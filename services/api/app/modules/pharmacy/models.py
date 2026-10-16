import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_uuid


class Dispensing(Base):
    """A pharmacist's record that a signed prescription was (or was not) handed over.

    Append-only: the newest row for a prescription is its dispensing status. It records the
    decision and who made it. It does not track which brand, batch or quantity (no stock system)."""

    __tablename__ = "dispensings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    prescription_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prescriptions.id"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), index=True)
    status: Mapped[str] = mapped_column(
        String(20)
    )  # DISPENSED | PARTIALLY_DISPENSED | NOT_DISPENSED
    note: Mapped[str | None] = mapped_column(String(300))
    dispensed_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
