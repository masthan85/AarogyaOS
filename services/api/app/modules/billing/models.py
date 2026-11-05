import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_uuid

MAX_PAISE = 10_000_000_00  # ₹1 crore on one line or one invoice: a typing slip, not a charge


class InvoiceCounter(Base):
    __tablename__ = "invoice_counters"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id"), primary_key=True
    )
    last_value: Mapped[int] = mapped_column(Integer, default=0)
    last_credit_note: Mapped[int] = mapped_column(Integer, default=0)


class Invoice(Base):
    """What a patient is charged for a visit. Money is whole paise; nothing here is clinical.

    DRAFT can be edited or discarded. ISSUED is frozen (a database trigger refuses edits) and can
    only be voided, and only while nothing has been paid. Tax is not calculated: staff enter the
    amounts."""

    __tablename__ = "invoices"
    __table_args__ = (
        Index("uq_invoices_number", "organisation_id", "number", unique=True),
        Index(
            "uq_invoices_one_per_encounter",
            "encounter_id",
            unique=True,
            postgresql_where=text("status <> 'VOID' AND encounter_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("encounters.id"))
    number: Mapped[str | None] = mapped_column(String(20))  # assigned when issued
    status: Mapped[str] = mapped_column(String(8), default="DRAFT")  # DRAFT | ISSUED | VOID
    total_paise: Mapped[int] = mapped_column(Integer, default=0)  # incl. tax; fixed when issued
    tax_paise: Mapped[int] = mapped_column(Integer, default=0)
    seller_gstin: Mapped[str | None] = mapped_column(String(15))  # as it stood when issued
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    issued_by: Mapped[uuid.UUID | None] = mapped_column()
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(String(200))
    voided_by: Mapped[uuid.UUID | None] = mapped_column()
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (Index("ix_invoice_lines_invoice", "invoice_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"))
    position: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_paise: Mapped[int] = mapped_column(Integer)
    tax_rate_bp: Mapped[int] = mapped_column(Integer, default=0)  # 1800 = 18%


class Payment(Base):
    """Money received against an issued invoice. Append-only: a mistake is not edited away."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount_paise: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(8))  # CASH | UPI | CARD | INSURER | OTHER
    reference: Mapped[str | None] = mapped_column(String(60))
    received_by: Mapped[uuid.UUID] = mapped_column()
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BillingSettings(Base):
    __tablename__ = "billing_settings"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id"), primary_key=True
    )
    gstin: Mapped[str | None] = mapped_column(String(15))
    legal_name: Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ServicePrice(Base):
    """The clinic's own price list. Lines copy the price, so changing it never alters an invoice."""

    __tablename__ = "service_prices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    name: Mapped[str] = mapped_column(String(200))
    price_paise: Mapped[int] = mapped_column(Integer)
    tax_rate_bp: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreditNote(Base):
    """Reduces what an issued invoice is worth (a later discount, a withdrawn charge)."""

    __tablename__ = "credit_notes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"))
    number: Mapped[str] = mapped_column(String(20))
    amount_paise: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(200))
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Refund(Base):
    """Money handed back. Only what has been paid beyond what is now owed can be refunded."""

    __tablename__ = "refunds"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"))
    amount_paise: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(8))
    reference: Mapped[str | None] = mapped_column(String(60))
    reason: Mapped[str] = mapped_column(String(200))
    refunded_by: Mapped[uuid.UUID] = mapped_column()
    refunded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CashClosing(Base):
    __tablename__ = "cash_closings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    business_date: Mapped[date] = mapped_column(Date)
    expected_cash_paise: Mapped[int] = mapped_column(Integer)
    counted_cash_paise: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(300))
    closed_by: Mapped[uuid.UUID] = mapped_column()
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InsuranceClaim(Base):
    """Tracks a claim made to an insurer or TPA. Nothing is sent anywhere: staff keep it current."""

    __tablename__ = "insurance_claims"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), index=True)
    insurer: Mapped[str] = mapped_column(String(120))
    policy_number: Mapped[str | None] = mapped_column(String(60))
    claim_reference: Mapped[str | None] = mapped_column(String(60))
    claimed_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="SUBMITTED")
    approved_paise: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
