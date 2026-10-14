import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, new_uuid

PURPOSES = (
    "MEDICAL_CARE",
    "AUDIO_RECORDING",
    "SPEECH_TRANSCRIPTION",
    "AI_PROCESSING",
    "AUDIO_RETENTION",
    "RESEARCH",
    "ANALYTICS",
    "AI_MODEL_IMPROVEMENT",
)


class ConsentPolicy(Base, TimestampMixin):
    """Versioned wording shown to the patient. Each purpose has its own text and version."""

    __tablename__ = "consent_policies"
    __table_args__ = (
        Index(
            "uq_consent_policy_version",
            "organisation_id",
            "purpose",
            "language",
            "version",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(25))
    language: Mapped[str] = mapped_column(String(35), default="en-IN")
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")  # ACTIVE | RETIRED
    # Installed template wording has not been reviewed by the organisation's legal advisers.
    legally_reviewed: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    created_by: Mapped[uuid.UUID | None] = mapped_column()


class Consent(Base):
    """One consent decision for one purpose. History is kept: a re-grant is a new row."""

    __tablename__ = "consents"
    __table_args__ = (Index("ix_consents_patient_purpose", "patient_id", "purpose", "granted_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"))
    purpose: Mapped[str] = mapped_column(String(25))
    policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("consent_policies.id"))
    policy_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="GRANTED")  # GRANTED | WITHDRAWN
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    granted_by_type: Mapped[str] = mapped_column(String(15))  # PATIENT | REPRESENTATIVE
    representative_name: Mapped[str | None] = mapped_column(String(200))
    representative_relationship: Mapped[str | None] = mapped_column(String(50))
    method: Mapped[str] = mapped_column(String(20))  # VERBAL_WITNESSED | ON_DEVICE | PAPER
    language_presented: Mapped[str] = mapped_column(String(35))
    captured_by: Mapped[uuid.UUID | None] = mapped_column()
    encounter_id: Mapped[uuid.UUID | None] = mapped_column()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_by: Mapped[uuid.UUID | None] = mapped_column()
    withdrawal_reason: Mapped[str | None] = mapped_column(String(300))
