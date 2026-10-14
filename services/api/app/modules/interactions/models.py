import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, new_uuid

SPEAKER_ROLES = ("DOCTOR", "PATIENT", "OTHER_STAFF", "FAMILY_MEMBER", "UNKNOWN")


class ClinicalInteraction(Base, TimestampMixin):
    """A bounded, consented, purposeful recording session."""

    __tablename__ = "clinical_interactions"
    __table_args__ = (Index("ix_interactions_patient", "patient_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"))
    # The visit it belongs to: an encounter for clinical purposes, an appointment at reception.
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("encounters.id"))
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("appointments.id"))
    purpose: Mapped[str] = mapped_column(String(15))  # RECEPTION | TRIAGE | CONSULTATION
    started_by: Mapped[uuid.UUID] = mapped_column()
    status: Mapped[str] = mapped_column(String(10), default="CREATED")
    # CREATED -> ACTIVE <-> PAUSED -> ENDED
    end_reason: Mapped[str | None] = mapped_column(String(30))
    pause_reason: Mapped[str | None] = mapped_column(String(30))
    language_hint: Mapped[str] = mapped_column(String(35), default="auto")
    ai_processing: Mapped[bool] = mapped_column(Boolean, default=False)
    # The consent rows this session relied on, frozen at start for later audit.
    consent_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    speech_provider: Mapped[str] = mapped_column(String(30))
    speech_model: Mapped[str] = mapped_column(String(60))
    is_development: Mapped[bool] = mapped_column(Boolean, default=False)
    retain_audio: Mapped[bool] = mapped_column(Boolean, default=False)
    retain_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recording_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_audio_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audio_seconds: Mapped[float] = mapped_column(Float, default=0)


class InteractionSpeaker(Base):
    """Who a provider speaker label is, as decided by a person. Never inferred from order."""

    __tablename__ = "interaction_speakers"

    interaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinical_interactions.id"), primary_key=True
    )
    speaker_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    role: Mapped[str] = mapped_column(String(15), default="UNKNOWN")
    label: Mapped[str | None] = mapped_column(String(80))
    assigned_by: Mapped[uuid.UUID | None] = mapped_column()
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TranscriptSegment(Base):
    """One final utterance. The text is immutable: corrections happen in derived layers."""

    __tablename__ = "transcript_segments"
    __table_args__ = (Index("uq_segment_seq", "interaction_id", "seq", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    interaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinical_interactions.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"))
    seq: Mapped[int] = mapped_column(Integer)
    speaker_id: Mapped[str | None] = mapped_column(String(30))
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    # Filled by the clinical normalisation step (Phase 5); the raw text above is never replaced.
    normalised_text: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(35))
    secondary_language: Mapped[str | None] = mapped_column(String(35))
    language_confidence: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    code_switch_spans: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    provider: Mapped[str] = mapped_column(String(30))
    provider_model: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AudioAsset(Base):
    """Retained audio. Exists only when organisation policy AND the patient's consent allow it."""

    __tablename__ = "audio_assets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    interaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinical_interactions.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"))
    storage_key: Mapped[str | None] = mapped_column(String(200))  # NULL once deleted
    bytes: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    retain_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_reason: Mapped[str | None] = mapped_column(String(40))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SpeechUsage(Base):
    """Metering per session: what it cost in audio time and how it performed. No content."""

    __tablename__ = "speech_usage"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    interaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinical_interactions.id"), unique=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column()
    encounter_id: Mapped[uuid.UUID | None] = mapped_column()
    user_id: Mapped[uuid.UUID] = mapped_column()
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(60))
    audio_seconds: Mapped[float] = mapped_column(Float, default=0)
    segments: Mapped[int] = mapped_column(Integer, default=0)
    first_segment_latency_ms: Mapped[int | None] = mapped_column(Integer)
    errors: Mapped[int] = mapped_column(SmallInteger, default=0)
    fell_back_from: Mapped[str | None] = mapped_column(String(30))
    # Provider price is a contract detail not yet known; stays NULL rather than being guessed.
    estimated_cost_paise: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
