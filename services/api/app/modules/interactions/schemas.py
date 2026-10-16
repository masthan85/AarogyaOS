import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Purpose = Literal["RECEPTION", "TRIAGE", "CONSULTATION"]
Role = Literal["DOCTOR", "PATIENT", "OTHER_STAFF", "FAMILY_MEMBER", "UNKNOWN"]


class InteractionCreate(BaseModel):
    patient_id: uuid.UUID
    purpose: Purpose
    encounter_id: uuid.UUID | None = None
    appointment_id: uuid.UUID | None = None
    language_hint: str | None = Field(default=None, max_length=35)
    ai_processing: bool = False


class StopIn(BaseModel):
    reason: str | None = Field(default=None, max_length=30)


class InteractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID | None
    appointment_id: uuid.UUID | None
    purpose: str
    status: str
    started_by: uuid.UUID
    ai_processing: bool
    speech_provider: str
    speech_model: str
    is_development: bool
    retain_audio: bool
    language_hint: str
    recording_started_at: datetime | None
    ended_at: datetime | None
    end_reason: str | None
    pause_reason: str | None
    audio_seconds: float


class AudioFormat(BaseModel):
    encoding: str = "pcm_s16le"
    sample_rate: int = 16000
    channels: int = 1
    max_frame_bytes: int = 65536


class StartOut(BaseModel):
    interaction: InteractionOut
    gateway_path: str
    audio_format: AudioFormat
    # Auth is the first WebSocket message, so the token never appears in a URL or a proxy log.
    auth: str = "first_message"


class SpeakerOut(BaseModel):
    speaker_id: str
    role: str
    label: str | None


class SegmentOut(BaseModel):
    id: uuid.UUID
    seq: int
    speaker_id: str | None
    speaker_role: str
    start_ms: int
    end_ms: int
    raw_text: str
    # A person's correction of raw_text, if any. raw_text itself never changes.
    corrected_text: str | None = None
    normalised_text: str | None
    language: str | None
    secondary_language: str | None
    language_confidence: float | None
    confidence: float | None
    code_switch_spans: list[dict[str, object]]
    provider: str


class PartialOut(BaseModel):
    text: str
    speaker_id: str | None
    language: str | None
    # A guess that may change; never a recorded fact.
    is_final: bool = False


class TranscriptOut(BaseModel):
    interaction_id: uuid.UUID
    status: str
    is_development: bool
    ai_processing: bool
    segments: list[SegmentOut]
    speakers: list[SpeakerOut]
    partial: PartialOut | None
    last_seq: int


class CorrectionIn(BaseModel):
    # None puts the segment back to exactly what was heard.
    text: str | None = Field(default=None, max_length=2000)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("Enter the corrected text, or send null to undo a correction")
        return v


class SpeakerAssign(BaseModel):
    role: Role
    label: str | None = Field(default=None, max_length=80)


class UsageRow(BaseModel):
    provider: str
    model: str
    sessions: int
    audio_seconds: float
    segments: int
    errors: int
    fallbacks: int
    avg_first_segment_latency_ms: float | None
    estimated_cost_paise: int | None
