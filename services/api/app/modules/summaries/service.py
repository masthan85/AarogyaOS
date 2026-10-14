"""Visit summary for the patient.

Built only from what the clinician has recorded and signed, plus the doctor's own instructions.
No unreviewed AI output goes in, and the model is not asked to write it. Translation is a separate,
declared step: if no translation service is connected the summary stays in the clinician's
language and says so. A doctor approves the final wording; an approved summary never changes.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.knowledge import NotAvailable, NullTranslationProvider, TranslationProvider
from app.core.context import Principal
from app.core.errors import Conflict, NotFound
from app.modules.ai.schemas import SummaryDraftIn, SummaryOut
from app.modules.audit.service import emit_event, record_audit
from app.modules.clinical.encounters import get_encounter, require_owner
from app.modules.clinical.models import (
    Condition,
    FollowUp,
    Prescription,
    PrescriptionItem,
    ServiceRequest,
)
from app.modules.summaries.models import PatientSummary

SOURCE_LANGUAGE = "en-IN"
_SETTLED = ("CLINICIAN_CONFIRMED", "CLINICIAN_EDITED")


def _org(principal: Principal) -> uuid.UUID:
    assert principal.org_id is not None
    return principal.org_id


def build_english(session: Session, encounter_id: uuid.UUID, instructions: str | None) -> str:
    enc = get_encounter(session, encounter_id)
    lines: list[str] = ["Your visit summary", ""]
    conditions = session.scalars(
        select(Condition).where(
            Condition.encounter_id == enc.id,
            Condition.is_current.is_(True),
            Condition.certainty.in_(["CONFIRMED", "PROVISIONAL"]),
            (Condition.source == "DOCTOR_ENTERED") | Condition.verification_state.in_(_SETTLED),
        )
    ).all()
    if conditions:
        lines += ["What the doctor found:", *[f"- {c.display}" for c in conditions], ""]
    items = session.execute(
        select(PrescriptionItem)
        .join(Prescription, Prescription.id == PrescriptionItem.prescription_id)
        .where(Prescription.encounter_id == enc.id, Prescription.status == "SIGNED")
        .order_by(PrescriptionItem.position)
    ).scalars()
    meds = [
        f"- {i.medicine_name}: {i.dose}, {i.frequency}"
        + (f", for {i.duration_days} days" if i.duration_days else "")
        + (f". {i.instructions}" if i.instructions else "")
        for i in items
    ]
    if meds:
        lines += ["Medicines prescribed:", *meds, ""]
    tests = session.scalars(
        select(ServiceRequest).where(
            ServiceRequest.encounter_id == enc.id,
            ServiceRequest.status.in_(["ORDERED", "RESULTED"]),
        )
    ).all()
    if tests:
        lines += ["Tests advised:", *[f"- {t.name}" for t in tests], ""]
    follow = session.scalars(
        select(FollowUp).where(FollowUp.encounter_id == enc.id, FollowUp.status == "PENDING")
    ).all()
    if follow:
        lines += ["Follow-up:", *[f"- {f.due_date:%d %b %Y}: {f.reason}" for f in follow], ""]
    if instructions and instructions.strip():
        lines += ["Advice from your doctor:", instructions.strip(), ""]
    lines.append("If you feel worse or are worried, contact the clinic or seek urgent care.")
    return "\n".join(lines)


def _translate(translator: TranslationProvider, text: str, target: str) -> tuple[str, str]:
    if target.split("-")[0].lower() == SOURCE_LANGUAGE.split("-")[0]:
        return text, "NOT_NEEDED"
    try:
        return asyncio.run(translator.translate(text, SOURCE_LANGUAGE, target)), "MACHINE_DRAFT"
    except NotAvailable:
        return text, "NOT_AVAILABLE"  # stays in the clinician's language; the UI says so


def draft(
    session: Session,
    principal: Principal,
    encounter_id: uuid.UUID,
    body: SummaryDraftIn,
    translator: TranslationProvider | None = None,
) -> SummaryOut:
    enc = get_encounter(session, encounter_id)
    require_owner(session, principal, enc)
    english = build_english(session, enc.id, body.instructions)
    content, status = _translate(translator or NullTranslationProvider(), english, body.language)
    version = (
        session.scalar(
            select(func.max(PatientSummary.version)).where(PatientSummary.encounter_id == enc.id)
        )
        or 0
    ) + 1
    row = PatientSummary(
        organisation_id=_org(principal),
        patient_id=enc.patient_id,
        encounter_id=enc.id,
        version=version,
        language=body.language if status == "MACHINE_DRAFT" else SOURCE_LANGUAGE,
        content=content,
        source_content=english,
        translation_status=status,
        created_by=principal.user_id,
    )
    session.add(row)
    session.flush()
    _log(session, principal, "PATIENT_SUMMARY_DRAFTED", row)
    session.commit()
    return SummaryOut.model_validate(row)


def _get(session: Session, principal: Principal, summary_id: uuid.UUID) -> PatientSummary:
    row = session.get(PatientSummary, summary_id)
    if row is None:
        raise NotFound("Summary not found")
    require_owner(session, principal, get_encounter(session, row.encounter_id))
    return row


def edit(session: Session, principal: Principal, summary_id: uuid.UUID, content: str) -> SummaryOut:
    row = _get(session, principal, summary_id)
    if row.status != "DRAFT":
        raise Conflict("Only a draft can be edited. Make a new draft instead.")
    row.content = content.strip()
    if row.translation_status == "MACHINE_DRAFT":
        row.translation_status = "CLINICIAN_EDITED"
    _log(session, principal, "PATIENT_SUMMARY_EDITED", row)
    session.commit()
    return SummaryOut.model_validate(row)


def approve(session: Session, principal: Principal, summary_id: uuid.UUID) -> SummaryOut:
    row = _get(session, principal, summary_id)
    if row.status != "DRAFT":
        raise Conflict("Only a draft can be approved")
    for old in session.scalars(
        select(PatientSummary).where(
            PatientSummary.encounter_id == row.encounter_id,
            PatientSummary.language == row.language,
            PatientSummary.status == "APPROVED",
        )
    ):
        old.status = "SUPERSEDED"
    row.status, row.approved_by, row.approved_at = "APPROVED", principal.user_id, datetime.now(UTC)
    _log(session, principal, "PATIENT_SUMMARY_APPROVED", row)
    session.commit()
    return SummaryOut.model_validate(row)


def list_for_encounter(
    session: Session, principal: Principal, encounter_id: uuid.UUID
) -> list[SummaryOut]:
    enc = get_encounter(session, encounter_id)
    require_owner(session, principal, enc)
    rows = session.scalars(
        select(PatientSummary)
        .where(PatientSummary.encounter_id == enc.id)
        .order_by(PatientSummary.version)
    )
    return [SummaryOut.model_validate(r) for r in rows]


def _log(session: Session, principal: Principal, event: str, row: PatientSummary) -> None:
    org_id = _org(principal)
    emit_event(
        session,
        org_id=org_id,
        event_type=event,
        aggregate_type="patient_summary",
        aggregate_id=row.id,
        patient_id=row.patient_id,
        encounter_id=row.encounter_id,
        actor_user_id=principal.user_id,
        payload={"version": row.version, "language": row.language},
    )
    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action=event,
        resource_type="patient_summary",
        resource_id=row.id,
    )
