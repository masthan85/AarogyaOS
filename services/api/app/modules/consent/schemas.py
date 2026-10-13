import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Purpose = Literal[
    "MEDICAL_CARE",
    "AUDIO_RECORDING",
    "SPEECH_TRANSCRIPTION",
    "AI_PROCESSING",
    "AUDIO_RETENTION",
    "RESEARCH",
    "ANALYTICS",
    "AI_MODEL_IMPROVEMENT",
]


class PolicyIn(BaseModel):
    purpose: Purpose
    language: str = Field(default="en-IN", max_length=35)
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=20, max_length=5000)
    # An administrator attests that counsel has reviewed this wording.
    legally_reviewed: bool = False


class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    purpose: str
    language: str
    version: int
    title: str
    body: str
    status: str
    legally_reviewed: bool


class ConsentIn(BaseModel):
    purpose: Purpose
    policy_id: uuid.UUID | None = None
    granted_by_type: Literal["PATIENT", "REPRESENTATIVE"] = "PATIENT"
    representative_name: str | None = Field(default=None, max_length=200)
    representative_relationship: str | None = Field(default=None, max_length=50)
    method: Literal["VERBAL_WITNESSED", "ON_DEVICE", "PAPER"]
    language_presented: str | None = Field(default=None, max_length=35)
    encounter_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _representative(self) -> "ConsentIn":
        if self.granted_by_type == "REPRESENTATIVE":
            if not (self.representative_name and self.representative_name.strip()):
                raise ValueError("Give the representative's name")
            if not (self.representative_relationship and self.representative_relationship.strip()):
                raise ValueError("Give the representative's relationship to the patient")
        return self


class WithdrawIn(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    purpose: str
    policy_id: uuid.UUID
    policy_version: int
    status: str
    granted_at: datetime
    granted_by_type: str
    representative_name: str | None
    representative_relationship: str | None
    method: str
    language_presented: str
    withdrawn_at: datetime | None
    withdrawal_reason: str | None


class PurposeStatus(BaseModel):
    purpose: str
    active: bool
    consent_id: uuid.UUID | None
    policy_version: int | None
    granted_at: datetime | None
    granted_by_type: str | None
    blocked_by: str | None  # the parent purpose that is not active
    wording_available: bool


class PatientConsents(BaseModel):
    status: list[PurposeStatus]
    history: list[ConsentOut]
    guardian_required: bool
