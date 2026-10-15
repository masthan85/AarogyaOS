"""Visit summary for the patient.

Built only from what the clinician has recorded and signed, plus the doctor's own instructions.
No unreviewed AI output goes in, and the model is not asked to write it. Translation is a separate,
declared step: if no translation service is connected the summary stays in the clinician's
language and says so. A doctor approves the final wording; an approved summary never changes.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.knowledge import NotAvailable, NullTranslationProvider, TranslationProvider
from app.core.context import Principal
from app.core.errors import Conflict, NotFound
from app.modules.ai.schemas import LetterDraftIn, SummaryDraftIn, SummaryOut
from app.modules.audit.service import emit_event, record_audit
from app.modules.clinical.encounters import get_encounter, require_owner
from app.modules.clinical.models import (
    Allergy,
    ClinicalNote,
    Condition,
    Encounter,
    FollowUp,
    InvestigationResult,
    Observation,
    PatientMedication,
    Prescription,
    PrescriptionItem,
    ServiceRequest,
)
from app.modules.identity.models import User
from app.modules.patients.models import Patient
from app.modules.scheduling.models import Practitioner
from app.modules.summaries.models import PatientSummary
from app.modules.tenancy.models import Facility

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
    version = _next_version(session, enc.id, "VISIT_SUMMARY")
    row = PatientSummary(
        kind="VISIT_SUMMARY",
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


def _next_version(session: Session, encounter_id: uuid.UUID, kind: str) -> int:
    top = session.scalar(
        select(func.max(PatientSummary.version)).where(
            PatientSummary.encounter_id == encounter_id, PatientSummary.kind == kind
        )
    )
    return (top or 0) + 1


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
            PatientSummary.kind == row.kind,
            PatientSummary.recipient.is_not_distinct_from(row.recipient),
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


# ---- referral letter ---------------------------------------------------------------------------

_LETTER_NOTES = ("HPI", "PAST_HISTORY", "EXAMINATION", "ASSESSMENT", "PLAN")
_NOTE_HEADINGS = {
    "HPI": "History",
    "PAST_HISTORY": "Past history",
    "EXAMINATION": "Examination",
    "ASSESSMENT": "Assessment",
    "PLAN": "Plan so far",
}


def _flag(fact: Any) -> str:
    """A receiving clinician must see what has and has not been checked."""
    if fact.verification_state == "UNVERIFIED" and fact.source == "PATIENT_REPORTED":
        return " (reported by the patient, not verified)"
    if fact.verification_state == "UNVERIFIED":
        return " (not yet verified)"
    return ""


def _settled(session: Session, model: Any, *where: Any) -> list[Any]:
    return list(
        session.scalars(
            select(model).where(
                model.is_current.is_(True),
                model.verification_state != "CLINICIAN_REJECTED",
                *where,
            )
        )
    )


def _result_line(r: Any) -> str:
    value = r.value_numeric if r.value_numeric is not None else r.value_text
    line = f"- {r.test_name}: {value} {r.unit or ''}".rstrip()
    if r.interpretation not in ("UNKNOWN", "NORMAL", "NOT_APPLICABLE"):
        line += f" ({r.interpretation.replace('_', ' ').lower()})"
    return line


def build_letter(
    session: Session, enc: Encounter, recipient: str, reason: str, instructions: str | None
) -> str:
    pat = session.get(Patient, enc.patient_id)
    prac = session.get(Practitioner, enc.practitioner_id) if enc.practitioner_id else None
    facility = session.get(Facility, enc.facility_id)
    user = session.get(User, prac.user_id) if prac else None
    assert pat is not None
    age = ""
    if pat.date_of_birth:
        today = datetime.now(UTC).date()
        years = (
            today.year
            - pat.date_of_birth.year
            - ((today.month, today.day) < (pat.date_of_birth.month, pat.date_of_birth.day))
        )
        age = f", {years} years{' (estimated)' if pat.dob_is_estimated else ''}"
    lines = [
        "Referral letter",
        f"Date: {datetime.now(UTC):%d %b %Y}",
        f"To: {recipient.strip()}",
        f"From: {('Dr ' + user.full_name) if user else 'Treating doctor'}"
        + (f", {facility.name}" if facility else ""),
        f"Patient: {pat.full_name} ({pat.administrative_gender}{age}), record number {pat.mrn}",
        "",
        "Reason for referral:",
        reason.strip(),
        "",
    ]
    conditions = _settled(session, Condition, Condition.patient_id == pat.id)
    if conditions:
        lines += [
            "Diagnoses and problems:",
            *[f"- {c.display} ({c.certainty.lower()}){_flag(c)}" for c in conditions],
            "",
        ]
    notes = _settled(session, ClinicalNote, ClinicalNote.encounter_id == enc.id)
    for note_type in _LETTER_NOTES:
        mine = [n for n in notes if n.note_type == note_type]
        if mine:
            lines += [
                f"{_NOTE_HEADINGS[note_type]}:",
                *[f"- {n.content}{_flag(n)}" for n in mine],
                "",
            ]
    allergies = _settled(session, Allergy, Allergy.patient_id == pat.id)
    real = [a for a in allergies if not a.is_nka]
    if real:
        lines += [
            "Allergies:",
            *[
                f"- {a.substance} ({a.certainty.lower()}"
                + (f", reaction: {a.reaction}" if a.reaction else "")
                + f"){_flag(a)}"
                for a in real
            ],
            "",
        ]
    elif any(a.is_nka for a in allergies):
        lines += ["Allergies: no known allergies recorded.", ""]
    else:
        lines += ["Allergies: allergy status has not been recorded.", ""]
    meds = _settled(
        session,
        PatientMedication,
        PatientMedication.patient_id == pat.id,
        PatientMedication.status == "ACTIVE",
    )
    if meds:
        lines += [
            "Current medicines:",
            *[
                "- " + " ".join(x for x in (m.name, m.dose, m.route, m.frequency) if x) + _flag(m)
                for m in meds
            ],
            "",
        ]
    vitals = _settled(session, Observation, Observation.encounter_id == enc.id)
    if vitals:
        lines += [
            "Observations this visit:",
            *[
                f"- {v.code.replace('_', ' ').title()}: {v.value:g} {v.unit}"
                + (
                    f" ({v.interpretation.replace('_', ' ').lower()})"
                    if v.interpretation not in ("UNKNOWN", "NORMAL", "NOT_APPLICABLE")
                    else ""
                )
                for v in vitals
            ],
            "",
        ]
    tests = session.scalars(
        select(ServiceRequest).where(
            ServiceRequest.encounter_id == enc.id,
            ServiceRequest.status.in_(["ORDERED", "RESULTED"]),
        )
    ).all()
    if tests:
        lines += ["Tests requested this visit:", *[f"- {t.name}" for t in tests], ""]
    results = session.scalars(
        select(InvestigationResult).where(
            InvestigationResult.service_request_id.in_([t.id for t in tests])
        )
    ).all()
    if results:
        lines += ["Results:", *[_result_line(r) for r in results], ""]
    if instructions and instructions.strip():
        lines += ["Further information from the doctor:", instructions.strip(), ""]
    lines += ["", f"{('Dr ' + user.full_name) if user else 'Treating doctor'}"]
    if prac and prac.registration_number:
        lines.append(f"Registration number: {prac.registration_number}")
    return "\n".join(lines)


def draft_letter(
    session: Session, principal: Principal, encounter_id: uuid.UUID, body: LetterDraftIn
) -> SummaryOut:
    """Built only from recorded, non-rejected data and the doctor's words. No model is involved;
    the doctor edits and approves it, and an approved letter is frozen like a summary."""
    enc = get_encounter(session, encounter_id)
    require_owner(session, principal, enc)
    text = build_letter(session, enc, body.recipient, body.reason, body.instructions)
    row = PatientSummary(
        kind="REFERRAL_LETTER",
        recipient=body.recipient.strip(),
        organisation_id=_org(principal),
        patient_id=enc.patient_id,
        encounter_id=enc.id,
        version=_next_version(session, enc.id, "REFERRAL_LETTER"),
        language=SOURCE_LANGUAGE,
        content=text,
        source_content=text,
        translation_status="NOT_NEEDED",
        created_by=principal.user_id,
    )
    session.add(row)
    session.flush()
    _log(session, principal, "REFERRAL_LETTER_DRAFTED", row)
    session.commit()
    return SummaryOut.model_validate(row)
