"""Provenance and correction rules shared by all clinical facts."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.modules.audit.service import emit_event, record_audit
from app.modules.clinical.models import (
    Allergy,
    ClinicalNote,
    Condition,
    Observation,
    PatientMedication,
)

# Sources a client may claim. DEVICE_RECORDED, LAB_RESULT and AI_EXTRACTED are set by the
# server alone: a user must not be able to dress up a typed value as a device reading.
CLIENT_SOURCES = {"PATIENT_REPORTED", "STAFF_ENTERED", "DOCTOR_ENTERED", "EXTERNAL_RECORD"}

KINDS: dict[str, type] = {
    "observations": Observation,
    "notes": ClinicalNote,
    "conditions": Condition,
    "allergies": Allergy,
    "medications": PatientMedication,
}

_NOT_COPIED = {
    "id",
    "source",
    "verification_state",
    "recorded_by",
    "recorded_at",
    "verified_by",
    "verified_at",
    "rejection_reason",
    "supersedes_id",
    "is_current",
}


def default_source(principal: Principal) -> str:
    return "DOCTOR_ENTERED" if "doctor" in principal.roles else "STAFF_ENTERED"


def provenance_for_new(principal: Principal, requested: str | None) -> dict[str, Any]:
    """Source and verification for a fact typed in by a human.

    A doctor's own entry counts as clinician-confirmed; anyone else's starts UNVERIFIED and
    waits for a clinician to confirm it. What the *patient* said keeps PATIENT_REPORTED even
    when a doctor typed it, so the origin of the statement is never lost.
    """
    if requested is not None and requested not in CLIENT_SOURCES:
        raise AppError("That source cannot be set by a user")
    confirmed = principal.has("condition:confirm")
    return {
        "source": requested or default_source(principal),
        "verification_state": "CLINICIAN_CONFIRMED" if confirmed else "UNVERIFIED",
        "recorded_by": principal.user_id,
        "verified_by": principal.user_id if confirmed else None,
        "verified_at": datetime.now(UTC) if confirmed else None,
    }


def current_filter(model: Any) -> list[Any]:
    """Facts that describe the patient now: latest version, and not rejected."""
    return [model.is_current.is_(True), model.verification_state != "CLINICIAN_REJECTED"]


def get_fact[F](session: Session, model: type[F], fact_id: uuid.UUID) -> F:
    row = session.get(model, fact_id)
    if row is None:
        raise NotFound("Record not found")
    return row


def supersede(session: Session, principal: Principal, old: Any, changes: dict[str, Any]) -> Any:
    """Correct a fact by inserting a new version; the old row's content is never altered."""
    if not old.is_current or old.verification_state == "CLINICIAN_REJECTED":
        raise Conflict("This entry has already been replaced or rejected")
    mapper = inspect(type(old))
    values = {c.key: getattr(old, c.key) for c in mapper.column_attrs if c.key not in _NOT_COPIED}
    values.update(changes)
    clinician = principal.has("fact:verify")
    new = type(old)(
        **values,
        source=default_source(principal) if old.source == "AI_EXTRACTED" else old.source,
        verification_state="CLINICIAN_EDITED" if clinician else "REQUIRES_REVIEW",
        recorded_by=principal.user_id,
        verified_by=principal.user_id if clinician else None,
        verified_at=datetime.now(UTC) if clinician else None,
        supersedes_id=old.id,
        is_current=True,
    )
    old.is_current = False
    session.add(new)
    session.flush()
    return new


def verify_fact(
    session: Session,
    principal: Principal,
    kind: str,
    fact_id: uuid.UUID,
    action: str,
    reason: str | None,
) -> Any:
    model = KINDS.get(kind)
    if model is None:
        raise NotFound("Unknown record type")
    if kind == "conditions" and not principal.has("condition:confirm"):
        raise Forbidden("Only a doctor can confirm or reject a diagnosis")
    row: Any = get_fact(session, model, fact_id)
    if not row.is_current:
        raise Conflict("Only the latest version of an entry can be verified")
    if action == "reject":
        if not reason or not reason.strip():
            raise AppError("Give a reason for rejecting this entry")
        row.verification_state = "CLINICIAN_REJECTED"
        row.rejection_reason = reason.strip()
    else:
        row.verification_state = "CLINICIAN_CONFIRMED"
        row.rejection_reason = None
    row.verified_by = principal.user_id
    row.verified_at = datetime.now(UTC)
    org_id = principal.org_id
    assert org_id is not None
    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action=f"FACT_{'REJECTED' if action == 'reject' else 'CONFIRMED'}",
        resource_type=kind,
        resource_id=row.id,
        after={"verification_state": row.verification_state},
    )
    emit_event(
        session,
        org_id=org_id,
        event_type="CLINICAL_FACT_VERIFIED",
        aggregate_type=kind,
        aggregate_id=row.id,
        patient_id=row.patient_id,
        encounter_id=row.encounter_id,
        actor_user_id=principal.user_id,
        payload={"action": action},
    )
    session.flush()
    return row
