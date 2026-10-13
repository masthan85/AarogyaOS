import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_uuid


class AiExtraction(Base):
    """One extraction run over a window of transcript segments. Never edited afterwards."""

    __tablename__ = "ai_extractions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    interaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinical_interactions.id"), index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"))
    encounter_id: Mapped[uuid.UUID | None] = mapped_column()
    triggered_by: Mapped[uuid.UUID] = mapped_column()
    task: Mapped[str] = mapped_column(String(30), default="clinical_extraction")
    prompt_version: Mapped[str] = mapped_column(String(30))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(60))
    is_development: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(10))  # OK | FAILED
    error_code: Mapped[str | None] = mapped_column(String(40))  # a code, never vendor text
    from_seq: Mapped[int] = mapped_column(Integer)
    to_seq: Mapped[int] = mapped_column(Integer)
    proposed: Mapped[int] = mapped_column(Integer, default=0)
    kept: Mapped[int] = mapped_column(Integer, default=0)
    dropped: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiCandidate(Base):
    """A proposed fact. It is NOT part of the patient's record until a clinician acts on it."""

    __tablename__ = "ai_candidates"
    __table_args__ = (
        Index("ix_ai_candidates_interaction", "interaction_id", "status"),
        Index("ix_ai_candidates_encounter", "encounter_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    extraction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_extractions.id"))
    interaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinical_interactions.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"))
    encounter_id: Mapped[uuid.UUID | None] = mapped_column()
    kind: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(String(300))
    assertion: Mapped[str] = mapped_column(String(10))
    subject: Mapped[str] = mapped_column(String(15), default="PATIENT")
    attributes: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    original_term: Mapped[str | None] = mapped_column(String(120))
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    risk_flags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    dedupe_key: Mapped[str] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # --- review state: the only columns that may change after creation ---
    status: Mapped[str] = mapped_column(
        String(10), default="PENDING"
    )  # PENDING|ACCEPTED|EDITED|REJECTED
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column()
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(String(300))
    edited_text: Mapped[str | None] = mapped_column(String(300))
    result_kind: Mapped[str | None] = mapped_column(String(30))  # which record it became
    result_id: Mapped[uuid.UUID | None] = mapped_column()


class AiSuggestion(Base):
    __tablename__ = "ai_suggestions"
    __table_args__ = (Index("ix_ai_suggestions_encounter", "encounter_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"))
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"))
    interaction_id: Mapped[uuid.UUID | None] = mapped_column()
    category: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(160))
    explanation: Mapped[str] = mapped_column(String(800))
    uncertainty: Mapped[str] = mapped_column(String(6), default="MEDIUM")
    uncertainty_note: Mapped[str | None] = mapped_column(String(300))
    # What it relies on in THIS patient's data, and which approved reference passages it cites.
    supporting_context: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)
    evidence_sources: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)
    payload: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    origin: Mapped[str] = mapped_column(String(14))  # DETERMINISTIC | MODEL
    provider: Mapped[str | None] = mapped_column(String(30))
    model: Mapped[str | None] = mapped_column(String(60))
    prompt_version: Mapped[str | None] = mapped_column(String(30))
    dedupe_key: Mapped[str] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(10), default="PENDING")
    acted_by: Mapped[uuid.UUID | None] = mapped_column()
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiSuggestionAction(Base):
    """Append-only record of what a clinician did with a suggestion."""

    __tablename__ = "ai_suggestion_actions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    suggestion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_suggestions.id"), index=True)
    action: Mapped[str] = mapped_column(String(10))  # ACCEPT | EDIT | REJECT | DISMISS
    actor_user_id: Mapped[uuid.UUID] = mapped_column()
    previous: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    new: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(String(300))
    result_kind: Mapped[str | None] = mapped_column(String(30))
    result_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiUsage(Base):
    """One row per model call: what it cost and how it behaved. No content."""

    __tablename__ = "ai_usage"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    feature: Mapped[str] = mapped_column(String(20))  # extraction | suggestions
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(60))
    patient_id: Mapped[uuid.UUID | None] = mapped_column()
    encounter_id: Mapped[uuid.UUID | None] = mapped_column()
    interaction_id: Mapped[uuid.UUID | None] = mapped_column()
    user_id: Mapped[uuid.UUID] = mapped_column()
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    tokens_are_estimates: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10))  # OK | INVALID | ERROR | TIMEOUT
    estimated_cost_paise: Mapped[int | None] = mapped_column(Integer)  # NULL until a price is known
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeDocument(Base):
    """A reference document. Only APPROVED documents are ever retrieved for decision support."""

    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    publisher: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(300))
    version: Mapped[str] = mapped_column(String(40))
    publication_date: Mapped[date | None] = mapped_column(Date)
    effective_date: Mapped[date | None] = mapped_column(Date)
    country: Mapped[str] = mapped_column(String(2), default="IN")
    specialty: Mapped[str | None] = mapped_column(String(80))
    # ORG_LICENSED | PUBLIC_DOMAIN | SYNTHETIC_TEST. Content is never scraped from the open web.
    licence: Mapped[str] = mapped_column(String(20))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column()
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # Float arrays ranked in Python: fine for an organisation-sized corpus. pgvector replaces this
    # behind the same interface in Phase 7 (it is not installed in the development database).
    embedding: Mapped[list[float]] = mapped_column(ARRAY(Float))
    embedding_model: Mapped[str] = mapped_column(String(60))
