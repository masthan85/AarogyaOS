import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_uuid


class LegalHold(Base):
    """While a hold is active, nothing about this patient may be deleted by a retention job."""

    __tablename__ = "legal_holds"
    __table_args__ = (Index("ix_legal_holds_patient", "patient_id", "released_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"))
    reason: Mapped[str] = mapped_column(String(300))
    placed_by: Mapped[uuid.UUID] = mapped_column()
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    released_by: Mapped[uuid.UUID | None] = mapped_column()
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_reason: Mapped[str | None] = mapped_column(String(300))
