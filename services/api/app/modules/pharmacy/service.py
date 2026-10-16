import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import Conflict, NotFound
from app.modules.audit.service import record_audit
from app.modules.clinical.models import Prescription
from app.modules.identity.models import User
from app.modules.pharmacy.models import Dispensing

Status = Literal["DISPENSED", "PARTIALLY_DISPENSED", "NOT_DISPENSED"]


class DispenseIn(BaseModel):
    status: Status
    note: str | None = Field(default=None, max_length=300)


class DispensingOut(BaseModel):
    id: uuid.UUID
    prescription_id: uuid.UUID
    status: str
    note: str | None
    dispensed_by_name: str
    created_at: datetime


def _out(session: Session, rows: list[Dispensing]) -> list[DispensingOut]:
    ids = {r.dispensed_by for r in rows}
    names = (
        dict(
            session.execute(select(User.id, User.full_name).where(User.id.in_(ids))).tuples().all()
        )
        if ids
        else {}
    )
    return [
        DispensingOut(
            id=r.id,
            prescription_id=r.prescription_id,
            status=r.status,
            note=r.note,
            dispensed_by_name=names.get(r.dispensed_by, "Unknown"),
            created_at=r.created_at,
        )
        for r in rows
    ]


def record(
    session: Session, principal: Principal, rx_id: uuid.UUID, body: DispenseIn
) -> DispensingOut:
    assert principal.org_id is not None
    rx = session.scalar(select(Prescription).where(Prescription.id == rx_id).with_for_update())
    if rx is None or rx.status == "DRAFT":
        raise NotFound("Prescription not found")  # drafts are invisible outside the doctor
    if rx.status == "VOIDED":
        raise Conflict("This prescription was voided by the doctor. Do not dispense it.")
    latest = session.scalar(
        select(Dispensing)
        .where(Dispensing.prescription_id == rx.id)
        .order_by(Dispensing.created_at.desc(), Dispensing.id.desc())
    )
    if latest is not None and latest.status == "DISPENSED":
        raise Conflict("This prescription has already been fully dispensed")
    row = Dispensing(
        organisation_id=principal.org_id,
        prescription_id=rx.id,
        patient_id=rx.patient_id,
        status=body.status,
        note=body.note.strip() if body.note and body.note.strip() else None,
        dispensed_by=principal.user_id,
    )
    session.add(row)
    session.flush()
    record_audit(
        session,
        principal.meta,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        action=f"PRESCRIPTION_{body.status}",
        resource_type="prescriptions",
        resource_id=rx.id,
    )
    session.commit()
    return _out(session, [row])[0]


def for_patient(session: Session, patient_id: uuid.UUID) -> list[DispensingOut]:
    rows = session.scalars(
        select(Dispensing)
        .where(Dispensing.patient_id == patient_id)
        .order_by(Dispensing.created_at.desc())
        .limit(200)
    ).all()
    return _out(session, list(rows))
