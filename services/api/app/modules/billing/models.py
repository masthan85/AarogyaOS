import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_uuid

MAX_PAISE = 10_000_000_00  # ₹1 crore on one line or one invoice: a typing slip, not a charge


class InvoiceCounter(Base):
    __tablename__ = "invoice_counters"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id"), primary_key=True
    )
    last_value: Mapped[int] = mapped_column(Integer, default=0)


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
    total_paise: Mapped[int] = mapped_column(Integer, default=0)  # fixed when issued
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


class Payment(Base):
    """Money received against an issued invoice. Append-only: a mistake is not edited away."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount_paise: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(8))  # CASH | UPI | CARD | OTHER
    reference: Mapped[str | None] = mapped_column(String(60))
    received_by: Mapped[uuid.UUID] = mapped_column()
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
