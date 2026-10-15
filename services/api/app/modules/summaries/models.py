import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_uuid


class PatientSummary(Base):
    """A visit summary for the patient: built from clinician-approved data, approved by a doctor."""

    __tablename__ = "patient_summaries"
    __table_args__ = (Index("ix_patient_summaries_encounter", "encounter_id", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"))
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"))
    # VISIT_SUMMARY (for the patient) | REFERRAL_LETTER (for another clinician)
    kind: Mapped[str] = mapped_column(String(16), default="VISIT_SUMMARY")
    recipient: Mapped[str | None] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    language: Mapped[str] = mapped_column(String(35), default="en-IN")
    content: Mapped[str] = mapped_column(Text)
    # The clinician-approved wording this was derived from; kept whenever a translation exists.
    source_content: Mapped[str] = mapped_column(Text)
    translation_status: Mapped[str] = mapped_column(String(20), default="NOT_TRANSLATED")
    status: Mapped[str] = mapped_column(
        String(10), default="DRAFT"
    )  # DRAFT | APPROVED | SUPERSEDED
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    approved_by: Mapped[uuid.UUID | None] = mapped_column()
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
