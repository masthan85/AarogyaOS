import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.clinical.schemas import SafetyWarning


class AnalyseOut(BaseModel):
    status: Literal["OK", "FAILED", "NOTHING_NEW"]
    extraction_id: uuid.UUID | None = None
    new_candidates: int = 0
    dropped: dict[str, int] = {}
    message: str | None = None
    is_development: bool = False


class EvidenceOut(BaseModel):
    segment_id: str
    seq: int
    quote: str
    speaker_role: str


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    interaction_id: uuid.UUID
    encounter_id: uuid.UUID | None
    kind: str
    text: str
    assertion: str
    subject: str
    attributes: dict[str, str]
    original_term: str | None
    evidence: list[EvidenceOut]
    risk_flags: list[str]
    status: str
    edited_text: str | None
    result_kind: str | None
    created_at: datetime
    # For a pending FOLLOW_UP the doctor can schedule: how many days from today the wording says.
    follow_up_in_days: int | None = None


class ReviewIn(BaseModel):
    action: Literal["accept", "edit", "reject"]
    edited_text: str | None = Field(default=None, min_length=1, max_length=300)
    note: str | None = Field(default=None, max_length=300)
    # For a TREATMENT_DISCUSSED candidate: record it as a plan note (default) or put it on the
    # draft prescription. Either way nothing is signed.
    # For a FOLLOW_UP candidate: "follow_up" schedules a follow-up from the stated time.
    mode: Literal["note", "prescription_draft", "follow_up"] = "note"


class ReviewOut(BaseModel):
    candidate: CandidateOut
    result_kind: str | None
    result_id: uuid.UUID | None
    warnings: list[SafetyWarning] = []


class SuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    encounter_id: uuid.UUID
    category: str
    title: str
    explanation: str
    uncertainty: str
    uncertainty_note: str | None
    supporting_context: list[dict[str, str]]
    evidence_sources: list[dict[str, str]]
    payload: dict[str, str]
    warnings: list[str]
    origin: str
    provider: str | None
    model: str | None
    prompt_version: str | None
    status: str
    created_at: datetime


class SuggestionActionIn(BaseModel):
    action: Literal["accept", "edit", "reject", "dismiss"]
    title: str | None = Field(default=None, min_length=3, max_length=160)
    explanation: str | None = Field(default=None, min_length=3, max_length=800)
    reason: str | None = Field(default=None, max_length=300)


class SuggestionActionOut(BaseModel):
    suggestion: SuggestionOut
    result_kind: str | None = None
    result_id: uuid.UUID | None = None


class GenerateOut(BaseModel):
    created: int
    dropped: dict[str, int]
    model_used: bool
    message: str | None = None


class ReviewBundle(BaseModel):
    candidates: list[CandidateOut]
    suggestions: list[SuggestionOut]
    ai_enabled: bool
    suggestions_enabled: bool


class KnowledgeDocIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    publisher: str = Field(min_length=2, max_length=200)
    source: str = Field(min_length=2, max_length=300)
    version: str = Field(min_length=1, max_length=40)
    publication_date: datetime | None = None
    effective_date: datetime | None = None
    country: str = Field(default="IN", min_length=2, max_length=2)
    specialty: str | None = Field(default=None, max_length=80)
    licence: Literal["ORG_LICENSED", "PUBLIC_DOMAIN", "SYNTHETIC_TEST"]
    chunks: list[str] = Field(min_length=1, max_length=500)


class KnowledgeDocOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    publisher: str
    source: str
    version: str
    country: str
    specialty: str | None
    licence: str
    approved: bool
    retired_at: datetime | None
    created_by: uuid.UUID | None
    chunk_count: int = 0


class AiUsageRow(BaseModel):
    feature: str
    provider: str
    model: str
    calls: int
    ok: int
    failed: int
    input_tokens: int
    output_tokens: int
    tokens_are_estimates: bool
    avg_latency_ms: float | None
    estimated_cost_paise: int | None


class SummaryDraftIn(BaseModel):
    language: str = Field(default="en-IN", min_length=2, max_length=35)
    # What the doctor wants the patient told, in the doctor's own words. Always included verbatim.
    instructions: str | None = Field(default=None, max_length=2000)


class LetterDraftIn(BaseModel):
    recipient: str = Field(min_length=2, max_length=200)
    reason: str = Field(min_length=3, max_length=1500)
    # The doctor's own additional words, always included as written.
    instructions: str | None = Field(default=None, max_length=2000)


class SummaryEditIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class SummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    encounter_id: uuid.UUID
    kind: str
    recipient: str | None
    version: int
    language: str
    content: str
    source_content: str
    translation_status: str
    status: str
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    created_at: datetime


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=300)


class CitationOut(BaseModel):
    ref: str
    label: str
    date: str | None = None


class StatementOut(BaseModel):
    text: str
    citations: list[CitationOut]


class MatchOut(BaseModel):
    ref: str
    text: str
    date: str | None = None


class AskOut(BaseModel):
    # None when AI answering is off or unavailable; `matches` is a plain search and always present.
    answer: list[StatementOut] | None
    answered: bool
    matches: list[MatchOut]
    used_ai: bool
    message: str | None = None
    is_development: bool = False
