import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import Conflict, NotFound
from app.modules.audit.service import record_audit
from app.modules.billing.models import (
    MAX_PAISE,
    BillingSettings,
    CreditNote,
    Invoice,
    InvoiceCounter,
    InvoiceLine,
    Payment,
    Refund,
)
from app.modules.clinical.models import Encounter
from app.modules.identity.models import User
from app.modules.patients.models import Patient
from app.modules.scheduling.models import Practitioner

Method = Literal["CASH", "UPI", "CARD", "INSURER", "OTHER"]
MAX_LINES = 30


class LineIn(BaseModel):
    description: str = Field(min_length=2, max_length=200)
    quantity: int = Field(default=1, ge=1, le=999)
    unit_price_paise: int = Field(ge=0, le=MAX_PAISE)
    tax_rate_bp: int = Field(default=0, ge=0, le=2800, description="1800 means 18%")

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
    tax_rate_bp: int
    tax_paise: int
    total_paise: int  # before tax


class CreditNoteIn(BaseModel):
    amount_paise: int = Field(gt=0, le=MAX_PAISE)
    reason: str = Field(min_length=3, max_length=200)


class RefundIn(BaseModel):
    amount_paise: int = Field(gt=0, le=MAX_PAISE)
    method: Method
    reason: str = Field(min_length=3, max_length=200)
    reference: str | None = Field(default=None, max_length=60)


class CreditNoteOut(BaseModel):
    number: str
    amount_paise: int
    reason: str
    created_at: datetime


class RefundOut(BaseModel):
    amount_paise: int
    method: str
    reason: str
    reference: str | None
    refunded_at: datetime


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
    tax_paise: int
    total_paise: int  # including tax
    seller_gstin: str | None
    credited_paise: int
    net_paise: int  # total less credit notes
    paid_paise: int
    refunded_paise: int
    balance_paise: int  # still owed
    refund_due_paise: int  # paid beyond what is owed, available to refund
    payments: list[PaymentOut]
    credit_notes: list[CreditNoteOut]
    refunds: list[RefundOut]
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


def line_tax(quantity: int, unit_price_paise: int, tax_rate_bp: int) -> int:
    """Tax on one line in whole paise, rounded half up."""
    return (quantity * unit_price_paise * tax_rate_bp + 5000) // 10000


def totals(lines: list[Any]) -> tuple[int, int]:
    """(tax, grand total) for a set of lines."""
    net = sum(x.quantity * x.unit_price_paise for x in lines)
    tax = sum(line_tax(x.quantity, x.unit_price_paise, x.tax_rate_bp) for x in lines)
    return tax, net + tax


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
    tax, draft_total = totals(lines)
    total = draft_total if inv.status == "DRAFT" else inv.total_paise
    tax = tax if inv.status == "DRAFT" else inv.tax_paise
    paid = sum(p.amount_paise for p in payments)
    notes = list(
        session.scalars(
            select(CreditNote)
            .where(CreditNote.invoice_id == inv.id)
            .order_by(CreditNote.created_at)
        )
    )
    refunds = list(
        session.scalars(
            select(Refund).where(Refund.invoice_id == inv.id).order_by(Refund.refunded_at)
        )
    )
    credited = sum(n.amount_paise for n in notes)
    refunded = sum(r.amount_paise for r in refunds)
    net = total - credited
    held = paid - refunded  # money the clinic is still holding for this invoice
    live = inv.status != "VOID"
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
                tax_rate_bp=line.tax_rate_bp,
                tax_paise=line_tax(line.quantity, line.unit_price_paise, line.tax_rate_bp),
                total_paise=line.quantity * line.unit_price_paise,
            )
            for line in lines
        ],
        tax_paise=tax,
        total_paise=total,
        seller_gstin=inv.seller_gstin,
        credited_paise=credited,
        net_paise=net,
        paid_paise=paid,
        refunded_paise=refunded,
        balance_paise=max(net - held, 0) if live else 0,
        refund_due_paise=max(held - net, 0) if live else 0,
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
        credit_notes=[
            CreditNoteOut(
                number=n.number,
                amount_paise=n.amount_paise,
                reason=n.reason,
                created_at=n.created_at,
            )
            for n in notes
        ],
        refunds=[
            RefundOut(
                amount_paise=r.amount_paise,
                method=r.method,
                reason=r.reason,
                reference=r.reference,
                refunded_at=r.refunded_at,
            )
            for r in refunds
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
    if totals(body.lines)[1] > MAX_PAISE:
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
                tax_rate_bp=line.tax_rate_bp,
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
    tax, total = totals(lines)
    if not lines or total <= 0:
        raise Conflict("Add at least one charge with an amount before issuing")
    settings = session.get(BillingSettings, inv.organisation_id)
    inv.number = _next_number(session, inv.organisation_id)
    inv.total_paise = total
    inv.tax_paise = tax
    inv.seller_gstin = settings.gstin if settings else None
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
    if out(session, inv).balance_paise < body.amount_paise:
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
    if _paid(session, inv.id) > 0 or session.scalar(
        select(CreditNote.id).where(CreditNote.invoice_id == inv.id).limit(1)
    ):
        raise Conflict(
            "Money or a credit note is already recorded on this invoice. "
            "Issue a credit note for the full amount and refund what was paid."
        )
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


def _next_credit_number(session: Session, org_id: uuid.UUID) -> str:
    stmt = (
        pg_insert(InvoiceCounter)
        .values(organisation_id=org_id, last_value=0, last_credit_note=1)
        .on_conflict_do_update(
            index_elements=[InvoiceCounter.organisation_id],
            set_={"last_credit_note": InvoiceCounter.last_credit_note + 1},
        )
        .returning(InvoiceCounter.last_credit_note)
    )
    return f"CN-{session.execute(stmt).scalar_one():06d}"


def add_credit_note(
    session: Session, principal: Principal, invoice_id: uuid.UUID, body: CreditNoteIn
) -> InvoiceOut:
    inv = _get(session, invoice_id, lock=True)
    if inv.status != "ISSUED":
        raise Conflict("Only an issued invoice can be credited")
    if body.amount_paise > out(session, inv).net_paise:
        raise Conflict("A credit note cannot be more than what the invoice is still worth")
    session.add(
        CreditNote(
            organisation_id=inv.organisation_id,
            invoice_id=inv.id,
            number=_next_credit_number(session, inv.organisation_id),
            amount_paise=body.amount_paise,
            reason=body.reason.strip(),
            created_by=principal.user_id,
        )
    )
    session.flush()
    _audit(session, principal, "CREDIT_NOTE_ISSUED", inv)
    session.commit()
    return out(session, inv)


def add_refund(
    session: Session, principal: Principal, invoice_id: uuid.UUID, body: RefundIn
) -> InvoiceOut:
    inv = _get(session, invoice_id, lock=True)
    if inv.status != "ISSUED":
        raise Conflict("Only an issued invoice can be refunded")
    if body.amount_paise > out(session, inv).refund_due_paise:
        raise Conflict(
            "That is more than has been paid beyond what is owed. "
            "To refund a charge, issue a credit note for it first."
        )
    session.add(
        Refund(
            organisation_id=inv.organisation_id,
            invoice_id=inv.id,
            amount_paise=body.amount_paise,
            method=body.method,
            reason=body.reason.strip(),
            reference=body.reference.strip() if body.reference and body.reference.strip() else None,
            refunded_by=principal.user_id,
        )
    )
    session.flush()
    _audit(session, principal, "REFUND_RECORDED", inv)
    session.commit()
    return out(session, inv)
