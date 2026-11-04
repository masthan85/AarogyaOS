import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import Conflict, NotFound
from app.modules.audit.service import record_audit
from app.modules.billing.models import (
    MAX_PAISE,
    Invoice,
    InvoiceCounter,
    InvoiceLine,
    Payment,
)
from app.modules.clinical.models import Encounter
from app.modules.identity.models import User
from app.modules.patients.models import Patient
from app.modules.scheduling.models import Practitioner

Method = Literal["CASH", "UPI", "CARD", "OTHER"]
MAX_LINES = 30


class LineIn(BaseModel):
    description: str = Field(min_length=2, max_length=200)
    quantity: int = Field(default=1, ge=1, le=999)
    unit_price_paise: int = Field(ge=0, le=MAX_PAISE)

    @field_validator("description")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Describe the charge")
        return v


class LinesIn(BaseModel):
    lines: list[LineIn] = Field(max_length=MAX_LINES)


class DraftIn(BaseModel):
    patient_id: uuid.UUID
    encounter_id: uuid.UUID | None = None


class PaymentIn(BaseModel):
    amount_paise: int = Field(gt=0, le=MAX_PAISE)
    method: Method
    reference: str | None = Field(default=None, max_length=60)


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


class LineOut(BaseModel):
    description: str
    quantity: int
    unit_price_paise: int
    total_paise: int


class PaymentOut(BaseModel):
    id: uuid.UUID
    amount_paise: int
    method: str
    reference: str | None
    received_at: datetime


class InvoiceOut(BaseModel):
    id: uuid.UUID
    number: str | None
    status: str
    patient_id: uuid.UUID
    patient_name: str
    patient_mrn: str
    encounter_id: uuid.UUID | None
    lines: list[LineOut]
    total_paise: int
    paid_paise: int
    balance_paise: int
    payments: list[PaymentOut]
    created_at: datetime
    issued_at: datetime | None
    void_reason: str | None


class ToBillOut(BaseModel):
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str
    patient_mrn: str
    ended_at: datetime | None
    practitioner_name: str | None


def _org(principal: Principal) -> uuid.UUID:
    assert principal.org_id is not None
    return principal.org_id


def _audit(session: Session, principal: Principal, action: str, inv: Invoice) -> None:
    record_audit(
        session,
        principal.meta,
        org_id=_org(principal),
        actor_user_id=principal.user_id,
        action=action,
        resource_type="invoices",
        resource_id=inv.id,
    )


def _get(session: Session, invoice_id: uuid.UUID, *, lock: bool = False) -> Invoice:
    stmt = select(Invoice).where(Invoice.id == invoice_id)
    inv = session.scalar(stmt.with_for_update() if lock else stmt)
    if inv is None:
        raise NotFound("Invoice not found")
    return inv


def _lines(session: Session, invoice_id: uuid.UUID) -> list[InvoiceLine]:
    return list(
        session.scalars(
            select(InvoiceLine)
            .where(InvoiceLine.invoice_id == invoice_id)
            .order_by(InvoiceLine.position)
        )
    )


def _paid(session: Session, invoice_id: uuid.UUID) -> int:
    return int(
        session.scalar(
            select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
                Payment.invoice_id == invoice_id
            )
        )
        or 0
    )


def out(session: Session, inv: Invoice) -> InvoiceOut:
    patient = session.get(Patient, inv.patient_id)
    assert patient is not None
    lines = _lines(session, inv.id)
    payments = list(
        session.scalars(
            select(Payment).where(Payment.invoice_id == inv.id).order_by(Payment.received_at)
        )
    )
    draft_total = sum(line.quantity * line.unit_price_paise for line in lines)
    total = draft_total if inv.status == "DRAFT" else inv.total_paise
    paid = sum(p.amount_paise for p in payments)
    return InvoiceOut(
        id=inv.id,
        number=inv.number,
        status=inv.status,
        patient_id=inv.patient_id,
        patient_name=patient.full_name,
        patient_mrn=patient.mrn,
        encounter_id=inv.encounter_id,
        lines=[
            LineOut(
                description=line.description,
                quantity=line.quantity,
                unit_price_paise=line.unit_price_paise,
                total_paise=line.quantity * line.unit_price_paise,
            )
            for line in lines
        ],
        total_paise=total,
        paid_paise=paid,
        balance_paise=0 if inv.status == "VOID" else total - paid,
        payments=[
            PaymentOut(
                id=p.id,
                amount_paise=p.amount_paise,
                method=p.method,
                reference=p.reference,
                received_at=p.received_at,
            )
            for p in payments
        ],
        created_at=inv.created_at,
        issued_at=inv.issued_at,
        void_reason=inv.void_reason,
    )


def create_draft(session: Session, principal: Principal, body: DraftIn) -> InvoiceOut:
    patient = session.get(Patient, body.patient_id)
    if patient is None:
        raise NotFound("Patient not found")
    if body.encounter_id is not None:
        enc = session.get(Encounter, body.encounter_id)
        if enc is None or enc.patient_id != patient.id:
            raise NotFound("That visit was not found for this patient")
        clash = session.scalar(
            select(Invoice.id).where(Invoice.encounter_id == enc.id, Invoice.status != "VOID")
        )
        if clash is not None:
            raise Conflict("This visit already has an invoice")
    inv = Invoice(
        organisation_id=_org(principal),
        patient_id=patient.id,
        encounter_id=body.encounter_id,
        created_by=principal.user_id,
    )
    session.add(inv)
    session.flush()
    _audit(session, principal, "INVOICE_CREATED", inv)
    session.commit()
    return out(session, inv)


def set_lines(
    session: Session, principal: Principal, invoice_id: uuid.UUID, body: LinesIn
) -> InvoiceOut:
    inv = _get(session, invoice_id, lock=True)
    if inv.status != "DRAFT":
        raise Conflict("An issued invoice cannot be edited. Void it and write a new one.")
    if sum(x.quantity * x.unit_price_paise for x in body.lines) > MAX_PAISE:
        raise Conflict("The total is unusually large. Check the amounts.")
    session.execute(delete(InvoiceLine).where(InvoiceLine.invoice_id == inv.id))
    for i, line in enumerate(body.lines):
        session.add(
            InvoiceLine(
                organisation_id=inv.organisation_id,
                invoice_id=inv.id,
                position=i + 1,
                description=line.description,
                quantity=line.quantity,
                unit_price_paise=line.unit_price_paise,
            )
        )
    session.commit()
    return out(session, inv)


def _next_number(session: Session, org_id: uuid.UUID) -> str:
    stmt = (
        pg_insert(InvoiceCounter)
        .values(organisation_id=org_id, last_value=1)
        .on_conflict_do_update(
            index_elements=[InvoiceCounter.organisation_id],
            set_={"last_value": InvoiceCounter.last_value + 1},
        )
        .returning(InvoiceCounter.last_value)
    )
    return f"INV-{session.execute(stmt).scalar_one():06d}"


def issue(session: Session, principal: Principal, invoice_id: uuid.UUID) -> InvoiceOut:
    inv = _get(session, invoice_id, lock=True)
    if inv.status != "DRAFT":
        raise Conflict("This invoice has already been issued")
    lines = _lines(session, inv.id)
    total = sum(x.quantity * x.unit_price_paise for x in lines)
    if not lines or total <= 0:
        raise Conflict("Add at least one charge with an amount before issuing")
    inv.number = _next_number(session, inv.organisation_id)
    inv.total_paise = total
    inv.status = "ISSUED"
    inv.issued_by, inv.issued_at = principal.user_id, datetime.now(UTC)
    _audit(session, principal, "INVOICE_ISSUED", inv)
    session.commit()
    return out(session, inv)


def record_payment(
    session: Session, principal: Principal, invoice_id: uuid.UUID, body: PaymentIn
) -> InvoiceOut:
    inv = _get(session, invoice_id, lock=True)
    if inv.status != "ISSUED":
        raise Conflict("Payments can only be recorded on an issued invoice")
    balance = inv.total_paise - _paid(session, inv.id)
    if body.amount_paise > balance:
        raise Conflict("That is more than the amount still owed")
    session.add(
        Payment(
            organisation_id=inv.organisation_id,
            invoice_id=inv.id,
            amount_paise=body.amount_paise,
            method=body.method,
            reference=body.reference.strip() if body.reference and body.reference.strip() else None,
            received_by=principal.user_id,
        )
    )
    session.flush()
    _audit(session, principal, "PAYMENT_RECORDED", inv)
    session.commit()
    return out(session, inv)


def void(
    session: Session, principal: Principal, invoice_id: uuid.UUID, body: VoidIn
) -> InvoiceOut | None:
    """Discards a draft (returns None) or voids an issued invoice that has no payments."""
    inv = _get(session, invoice_id, lock=True)
    if inv.status == "VOID":
        raise Conflict("This invoice is already void")
    if inv.status == "DRAFT":
        session.execute(delete(InvoiceLine).where(InvoiceLine.invoice_id == inv.id))
        session.delete(inv)
        record_audit(
            session,
            principal.meta,
            org_id=_org(principal),
            actor_user_id=principal.user_id,
            action="INVOICE_DRAFT_DISCARDED",
            resource_type="invoices",
            resource_id=invoice_id,
        )
        session.commit()
        return None
    if _paid(session, inv.id) > 0:
        raise Conflict("Money has been received against this invoice. Refunds are not built yet.")
    inv.status = "VOID"
    inv.void_reason = body.reason.strip()
    inv.voided_by, inv.voided_at = principal.user_id, datetime.now(UTC)
    _audit(session, principal, "INVOICE_VOIDED", inv)
    session.commit()
    return out(session, inv)


def get(session: Session, invoice_id: uuid.UUID) -> InvoiceOut:
    return out(session, _get(session, invoice_id))


def list_invoices(
    session: Session,
    *,
    status: str | None = None,
    patient_id: uuid.UUID | None = None,
    unpaid: bool = False,
) -> list[InvoiceOut]:
    stmt = select(Invoice).order_by(Invoice.created_at.desc()).limit(100)
    if status:
        stmt = stmt.where(Invoice.status == status)
    if patient_id:
        stmt = stmt.where(Invoice.patient_id == patient_id)
    rows = [out(session, i) for i in session.scalars(stmt)]
    return [r for r in rows if r.status == "ISSUED" and r.balance_paise > 0] if unpaid else rows


def to_bill(session: Session, *, days: int = 7) -> list[ToBillOut]:
    """Visits finished in the last few days that have no invoice (a void one does not count)."""
    since = datetime.now(UTC) - timedelta(days=days)
    billed = select(Invoice.encounter_id).where(
        Invoice.encounter_id.is_not(None), Invoice.status != "VOID"
    )
    rows = session.execute(
        select(Encounter, Patient, User.full_name)
        .join(Patient, Patient.id == Encounter.patient_id)
        .outerjoin(Practitioner, Practitioner.id == Encounter.practitioner_id)
        .outerjoin(User, User.id == Practitioner.user_id)
        .where(
            Encounter.status == "COMPLETED",
            Encounter.ended_at >= since,
            Encounter.id.not_in(billed),
        )
        .order_by(Encounter.ended_at.desc())
        .limit(100)
    ).all()
    return [
        ToBillOut(
            encounter_id=e.id,
            patient_id=p.id,
            patient_name=p.full_name,
            patient_mrn=p.mrn,
            ended_at=e.ended_at,
            practitioner_name=name,
        )
        for e, p, name in rows
    ]
