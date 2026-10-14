"""Clinician review of AI candidates: the only way an AI-extracted statement becomes a fact.

Accepting or editing creates an ordinary clinical record with source AI_EXTRACTED, the transcript
evidence attached, and verification set by the clinician who acted. Rejecting creates nothing.
Nothing here signs, places or confirms anything: diagnoses enter as SUSPECTED, investigations as
DRAFT orders, treatments as plan notes or DRAFT prescription items.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.modules.ai.models import AiCandidate
from app.modules.ai.schemas import CandidateOut, ReviewOut
from app.modules.audit.service import emit_event, record_audit
from app.modules.clinical.encounters import open_encounter, require_owner
from app.modules.clinical.models import (
    Allergy,
    ClinicalNote,
    Condition,
    Encounter,
    PatientMedication,
    Prescription,
    PrescriptionItem,
    ServiceRequest,
)
from app.modules.clinical.safety import check_prescription
from app.modules.clinical.schemas import PrescriptionItemIn
from app.modules.interactions import service as interactions
from app.modules.interactions.models import ClinicalInteraction

# Kinds a nurse may review (triage-level). Everything else needs the encounter's own doctor.
NURSE_KINDS = frozenset({"CHIEF_COMPLAINT", "SYMPTOM", "VITAL_MENTIONED", "ALLERGY", "MEDICATION"})
_DOCTOR_NOTE_TYPE = {
    "CHIEF_COMPLAINT": "CHIEF_COMPLAINT",
    "SYMPTOM": "HPI",
    "MEDICAL_HISTORY": "PAST_HISTORY",
    "SURGICAL_HISTORY": "PAST_HISTORY",
    "FAMILY_HISTORY": "FAMILY_HISTORY",
    "SOCIAL_HISTORY": "SOCIAL_HISTORY",
    "PREVIOUS_TREATMENT": "PAST_HISTORY",
    "EXAMINATION_FINDING": "EXAMINATION",
    "VITAL_MENTIONED": "GENERAL",
    "FOLLOW_UP": "PLAN",
    "TREATMENT_DISCUSSED": "PLAN",
}
_PREFIX = {"PRESENT": "", "ABSENT": "Denies: ", "POSSIBLE": "Possible: ", "HISTORICAL": "Past: "}


def _org(principal: Principal) -> uuid.UUID:
    assert principal.org_id is not None
    return principal.org_id


def to_out(c: AiCandidate) -> CandidateOut:
    return CandidateOut.model_validate(c)


def _describe(c: AiCandidate, text: str) -> str:
    prefix = "Family history: " if c.subject == "FAMILY_MEMBER" else _PREFIX[c.assertion]
    detail = "; ".join(f"{k}: {v}" for k, v in c.attributes.items())
    return f"{prefix}{text}" + (f" ({detail})" if detail else "")


def _get(
    session: Session, principal: Principal, candidate_id: uuid.UUID
) -> tuple[AiCandidate, ClinicalInteraction]:
    cand = session.get(AiCandidate, candidate_id)
    if cand is None:
        raise NotFound("Candidate not found")
    ia = interactions.get_interaction(session, cand.interaction_id)
    if not interactions.can_access(session, principal, ia):
        raise NotFound("Candidate not found")  # same visibility as the transcript it came from
    return cand, ia


def list_for_interaction(
    session: Session, principal: Principal, interaction_id: uuid.UUID
) -> list[AiCandidate]:
    interactions.visible(session, principal, interaction_id)
    return list(
        session.scalars(
            select(AiCandidate)
            .where(AiCandidate.interaction_id == interaction_id)
            .order_by(AiCandidate.created_at, AiCandidate.id)
        )
    )


def list_for_encounter(
    session: Session, principal: Principal, encounter_id: uuid.UUID
) -> list[AiCandidate]:
    rows = session.scalars(
        select(AiCandidate)
        .where(AiCandidate.encounter_id == encounter_id)
        .order_by(AiCandidate.created_at, AiCandidate.id)
    ).all()
    allowed: dict[uuid.UUID, bool] = {}
    out = []
    for r in rows:
        if r.interaction_id not in allowed:
            allowed[r.interaction_id] = interactions.can_access(
                session, principal, interactions.get_interaction(session, r.interaction_id)
            )
        if allowed[r.interaction_id]:
            out.append(r)
    return out


def _evidence_ids(c: AiCandidate) -> list[str]:
    return [str(e["segment_id"]) for e in c.evidence if e.get("segment_id")]


def review(
    session: Session,
    principal: Principal,
    candidate_id: uuid.UUID,
    action: str,
    edited_text: str | None,
    note: str | None,
    mode: str,
) -> ReviewOut:
    cand, _ = _get(session, principal, candidate_id)
    if cand.status != "PENDING":
        raise Conflict("This item has already been reviewed")
    org_id = _org(principal)
    now = datetime.now(UTC)

    if action == "reject":
        cand.status, cand.reviewed_by, cand.reviewed_at, cand.review_note = (
            "REJECTED",
            principal.user_id,
            now,
            note,
        )
        _log(session, principal, "AI_CANDIDATE_REJECTED", cand, None)
        session.commit()
        return ReviewOut(candidate=to_out(cand), result_kind=None, result_id=None)

    if action == "edit" and not (edited_text and edited_text.strip()):
        raise AppError("Enter the corrected wording")
    if cand.encounter_id is None:
        raise Conflict("There is no open visit to record this in yet")
    enc = open_encounter(session, cand.encounter_id)
    text = (edited_text or cand.text).strip()
    edited = action == "edit"
    doctor_only = cand.kind not in NURSE_KINDS
    if doctor_only:
        if not principal.has("note:clinical"):
            raise Forbidden("Only the treating doctor can review this kind of finding")
        require_owner(session, principal, enc)

    result_kind, result_id, warnings = _materialise(
        session, principal, cand, enc, text, edited, mode
    )
    cand.status = "EDITED" if edited else "ACCEPTED"
    cand.reviewed_by, cand.reviewed_at, cand.review_note = principal.user_id, now, note
    cand.edited_text = text if edited else None
    cand.result_kind, cand.result_id = result_kind, result_id
    _log(
        session,
        principal,
        "AI_CANDIDATE_EDITED" if edited else "AI_CANDIDATE_ACCEPTED",
        cand,
        result_kind,
    )
    session.commit()
    del org_id
    return ReviewOut(
        candidate=to_out(cand), result_kind=result_kind, result_id=result_id, warnings=warnings
    )


def _log(
    session: Session, principal: Principal, event: str, c: AiCandidate, result_kind: str | None
) -> None:
    org_id = _org(principal)
    payload: dict[str, Any] = {"kind": c.kind, "assertion": c.assertion}
    if result_kind:
        payload["became"] = result_kind
    emit_event(
        session,
        org_id=org_id,
        event_type=event,
        aggregate_type="ai_candidate",
        aggregate_id=c.id,
        patient_id=c.patient_id,
        encounter_id=c.encounter_id,
        actor_user_id=principal.user_id,
        payload=payload,
    )
    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action=event,
        resource_type="ai_candidate",
        resource_id=c.id,
        after=payload,
        ai_involved=True,
    )


def _materialise(
    session: Session,
    principal: Principal,
    c: AiCandidate,
    enc: Encounter,
    text: str,
    edited: bool,
    mode: str,
) -> tuple[str, uuid.UUID, list[Any]]:
    org_id = _org(principal)
    now = datetime.now(UTC)
    prov: dict[str, Any] = {
        "source": "AI_EXTRACTED",
        "verification_state": "CLINICIAN_EDITED" if edited else "CLINICIAN_CONFIRMED",
        "recorded_by": principal.user_id,
        "verified_by": principal.user_id,
        "verified_at": now,
        "evidence_segment_ids": _evidence_ids(c),
    }
    base: dict[str, Any] = {
        "organisation_id": org_id,
        "patient_id": c.patient_id,
        "encounter_id": enc.id,
    }
    attrs = c.attributes

    if c.kind == "ALLERGY":
        if not principal.has("allergy:record"):
            raise Forbidden("You cannot record allergies")
        if c.assertion == "ABSENT":
            return _note(
                session, principal, c, enc, base, prov, "TRIAGE", f"Denies allergy: {text}"
            )
        certainty = {"PRESENT": "CONFIRMED", "POSSIBLE": "POSSIBLE", "HISTORICAL": "HISTORICAL"}[
            c.assertion
        ]
        row = Allergy(
            **base,
            **prov,
            substance=(attrs.get("substance") or text)[:200] if not edited else text[:200],
            category="MEDICATION",
            reaction=attrs.get("reaction"),
            severity=(attrs.get("severity") or "UNKNOWN").upper()
            if (attrs.get("severity") or "").upper() in {"MILD", "MODERATE", "SEVERE"}
            else "UNKNOWN",
            certainty=certainty,
        )
        session.add(row)
        session.flush()
        return "allergies", row.id, []

    if c.kind == "MEDICATION":
        if not principal.has("medication:record"):
            raise Forbidden("You cannot record medicines")
        if c.assertion == "ABSENT":
            return _note(session, principal, c, enc, base, prov, "TRIAGE", f"Not taking: {text}")
        med = PatientMedication(
            **base,
            **prov,
            name=(attrs.get("medicine") or text)[:200] if not edited else text[:200],
            dose=attrs.get("dose"),
            route=attrs.get("route"),
            frequency=attrs.get("frequency"),
            status="STOPPED" if c.assertion == "HISTORICAL" else "ACTIVE",
        )
        session.add(med)
        session.flush()
        return "medications", med.id, []

    if c.kind == "DIAGNOSIS_DISCUSSED":
        if c.assertion in ("ABSENT",):
            return _note(session, principal, c, enc, base, prov, "ASSESSMENT", _describe(c, text))
        if not principal.has("condition:record"):
            raise Forbidden("Only a doctor can record a diagnosis")
        cond = Condition(
            **base,
            **prov,
            display=(attrs.get("diagnosis") or text)[:300] if not edited else text[:300],
            category="DIAGNOSIS",
            certainty="SUSPECTED",  # never CONFIRMED from AI
            clinical_status="ACTIVE",
        )
        session.add(cond)
        session.flush()
        return "conditions", cond.id, []

    if c.kind == "INVESTIGATION_DISCUSSED":
        if not principal.has("order:write"):
            raise Forbidden("Only a doctor can draft an investigation")
        category = (attrs.get("category") or "OTHER").upper()
        order = ServiceRequest(
            organisation_id=org_id,
            patient_id=c.patient_id,
            encounter_id=enc.id,
            category=category if category in {"LAB", "RADIOLOGY", "OTHER"} else "OTHER",
            name=(attrs.get("test") or text)[:200] if not edited else text[:200],
            reason="Discussed in the consultation",
            status="DRAFT",  # a DRAFT: never placed
            source="AI_EXTRACTED",
            created_by=principal.user_id,
        )
        session.add(order)
        session.flush()
        return "service_requests", order.id, []

    if c.kind == "TREATMENT_DISCUSSED" and mode == "prescription_draft":
        return _prescription_draft(session, principal, c, enc, attrs)

    # Everything else is a clinical note. Doctors get the full note types; nurses the triage note.
    if principal.has("note:clinical"):
        note_type = _DOCTOR_NOTE_TYPE.get(c.kind, "GENERAL")
    elif principal.has("note:triage"):
        note_type = "CHIEF_COMPLAINT" if c.kind == "CHIEF_COMPLAINT" else "TRIAGE"
    else:
        raise Forbidden("You cannot add notes")
    return _note(session, principal, c, enc, base, prov, note_type, _describe(c, text))


def _note(
    session: Session,
    principal: Principal,
    c: AiCandidate,
    enc: Encounter,
    base: dict[str, Any],
    prov: dict[str, Any],
    note_type: str,
    content: str,
) -> tuple[str, uuid.UUID, list[Any]]:
    row = ClinicalNote(**base, **prov, note_type=note_type, content=content[:5000])
    session.add(row)
    session.flush()
    return "clinical_notes", row.id, []


def _prescription_draft(
    session: Session, principal: Principal, c: AiCandidate, enc: Encounter, attrs: dict[str, str]
) -> tuple[str, uuid.UUID, list[Any]]:
    if not principal.has("prescription:write"):
        raise Forbidden("Only a doctor can draft a prescription")
    me = require_owner(session, principal, enc)
    if enc.status != "IN_PROGRESS":
        raise Conflict("Start the consultation before prescribing")
    days = "".join(ch for ch in attrs.get("duration", "") if ch.isdigit())
    try:
        item = PrescriptionItemIn(
            medicine_name=attrs.get("medicine", ""),
            dose=attrs.get("dose", ""),
            route=(attrs.get("route") or "").upper(),
            frequency=attrs.get("frequency", ""),
            duration_days=int(days) if days else None,
        )
    except ValidationError as exc:
        missing = sorted({str(e["loc"][0]) for e in exc.errors()})
        raise AppError(
            "Cannot draft a prescription line: missing or invalid "
            + ", ".join(missing)
            + ". Add it as a plan note instead, or edit the details."
        ) from exc
    rx = session.scalar(
        select(Prescription)
        .where(Prescription.encounter_id == enc.id, Prescription.status == "DRAFT")
        .limit(1)
    )
    if rx is None:
        rx = Prescription(
            organisation_id=_org(principal),
            patient_id=c.patient_id,
            encounter_id=enc.id,
            practitioner_id=me.id,
            source="AI_EXTRACTED",
            created_by=principal.user_id,
        )
        session.add(rx)
        session.flush()
    position = (
        len(
            list(
                session.scalars(
                    select(PrescriptionItem.id).where(PrescriptionItem.prescription_id == rx.id)
                )
            )
        )
        + 1
    )
    session.add(
        PrescriptionItem(
            organisation_id=_org(principal),
            prescription_id=rx.id,
            position=position,
            **item.model_dump(),
        )
    )
    session.flush()
    items = list(
        session.scalars(
            select(PrescriptionItem)
            .where(PrescriptionItem.prescription_id == rx.id)
            .order_by(PrescriptionItem.position)
        )
    )
    checks = check_prescription(session, c.patient_id, items)
    return "prescriptions", rx.id, checks.warnings
