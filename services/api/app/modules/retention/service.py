import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import Conflict, NotFound
from app.modules.audit.service import record_audit
from app.modules.patients.models import Patient
from app.modules.retention.models import LegalHold


class HoldIn(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


class HoldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    reason: str
    placed_at: datetime
    released_at: datetime | None
    release_reason: str | None


def _audit(session: Session, principal: Principal, action: str, hold: LegalHold) -> None:
    assert principal.org_id is not None
    record_audit(
        session,
        principal.meta,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        action=action,
        resource_type="legal_holds",
        resource_id=hold.id,
        reason=hold.reason if action == "LEGAL_HOLD_PLACED" else hold.release_reason,
    )


def place(session: Session, principal: Principal, patient_id: uuid.UUID, body: HoldIn) -> HoldOut:
    assert principal.org_id is not None
    if session.get(Patient, patient_id) is None:
        raise NotFound("Patient not found")
    hold = LegalHold(
        organisation_id=principal.org_id,
        patient_id=patient_id,
        reason=body.reason.strip(),
        placed_by=principal.user_id,
    )
    session.add(hold)
    session.flush()
    _audit(session, principal, "LEGAL_HOLD_PLACED", hold)
    session.commit()
    return HoldOut.model_validate(hold)


def release(session: Session, principal: Principal, hold_id: uuid.UUID, body: HoldIn) -> HoldOut:
    hold = session.scalar(select(LegalHold).where(LegalHold.id == hold_id).with_for_update())
    if hold is None:
        raise NotFound("Legal hold not found")
    if hold.released_at is not None:
        raise Conflict("This hold has already been released")
    hold.released_by = principal.user_id
    hold.released_at = datetime.now(UTC)
    hold.release_reason = body.reason.strip()
    _audit(session, principal, "LEGAL_HOLD_RELEASED", hold)
    session.commit()
    return HoldOut.model_validate(hold)


def list_holds(
    session: Session, *, patient_id: uuid.UUID | None = None, active_only: bool = True
) -> list[HoldOut]:
    stmt = select(LegalHold).order_by(LegalHold.placed_at.desc()).limit(200)
    if patient_id:
        stmt = stmt.where(LegalHold.patient_id == patient_id)
    if active_only:
        stmt = stmt.where(LegalHold.released_at.is_(None))
    return [HoldOut.model_validate(h) for h in session.scalars(stmt)]


def held_patient_ids() -> object:
    """A subquery of patients under an active hold, for retention jobs to exclude."""
    return select(LegalHold.patient_id).where(LegalHold.released_at.is_(None))
