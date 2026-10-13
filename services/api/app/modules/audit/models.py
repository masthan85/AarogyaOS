import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_uuid


class AuditLog(Base):
    """Append-only record of who did what. Never updated or deleted by the app."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organisations.id"), index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    resource_type: Mapped[str] = mapped_column(String(60))
    resource_id: Mapped[uuid.UUID | None] = mapped_column()
    outcome: Mapped[str] = mapped_column(String(20), default="SUCCESS")
    reason: Mapped[str | None] = mapped_column(String(300))
    before: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    ai_involved: Mapped[bool] = mapped_column(default=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    correlation_id: Mapped[str | None] = mapped_column(String(64))


class ClinicalEvent(Base):
    """Outbox of domain events (PATIENT_REGISTERED, ...). Consumers mark `processed_at`."""

    __tablename__ = "clinical_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(60))
    aggregate_id: Mapped[uuid.UUID] = mapped_column()
    patient_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column()
    # Identifiers and codes only; never free-text PHI.
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
