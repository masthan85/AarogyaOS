import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.patients.normalise import normalise_abha_number, normalise_mobile

Gender = Literal["male", "female", "other", "unknown"]
LANG = r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$"
PHONE_FIELDS = ("mobile", "emergency_contact_phone")


class IdentifierIn(BaseModel):
    system: Literal["ABHA_NUMBER", "ABHA_ADDRESS", "EXTERNAL_MRN", "OTHER"]
    value: str = Field(min_length=3, max_length=100)

    @model_validator(mode="after")
    def _check(self) -> "IdentifierIn":
        self.value = self.value.strip()
        try:
            if self.system == "ABHA_NUMBER":
                self.value = normalise_abha_number(self.value)
            elif self.system == "ABHA_ADDRESS":
                if "@" not in self.value or " " in self.value:
                    raise ValueError("ABHA address must look like name@domain")
                self.value = self.value.lower()
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return self


class PatientFields(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    date_of_birth: date | None = None
    age_years: int | None = Field(default=None, ge=0, le=120)
    administrative_gender: Gender = "unknown"
    sex_at_birth: Literal["male", "female", "intersex", "unknown"] | None = None
    mobile: str | None = None
    address: str | None = Field(default=None, max_length=500)
    emergency_contact_name: str | None = Field(default=None, max_length=200)
    emergency_contact_phone: str | None = None
    emergency_contact_relationship: str | None = Field(default=None, max_length=50)
    preferred_language: str = Field(default="en-IN", pattern=LANG)
    spoken_languages: list[str] = Field(default_factory=list, max_length=8)
    communication_prefs: dict[str, bool] = Field(default_factory=dict)

    @field_validator("mobile", "emergency_contact_phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        return normalise_mobile(v) if v else None

    @field_validator("spoken_languages")
    @classmethod
    def _langs(cls, v: list[str]) -> list[str]:
        import re

        if any(not re.fullmatch(LANG, x) for x in v):
            raise ValueError("Invalid language tag")
        return sorted(set(v))

    @field_validator("date_of_birth")
    @classmethod
    def _dob(cls, v: date | None) -> date | None:
        if v and v > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return v


class PatientCreate(PatientFields):
    identifiers: list[IdentifierIn] = Field(default_factory=list, max_length=5)
    # Set only after the user has reviewed the duplicate candidates the server returned.
    confirm_not_duplicate: bool = False

    @model_validator(mode="after")
    def _need_age_or_dob(self) -> "PatientCreate":
        if self.date_of_birth is None and self.age_years is None:
            raise ValueError("Provide date of birth or estimated age")
        return self


class PatientUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    date_of_birth: date | None = None
    administrative_gender: Gender | None = None
    sex_at_birth: Literal["male", "female", "intersex", "unknown"] | None = None
    mobile: str | None = None
    address: str | None = Field(default=None, max_length=500)
    emergency_contact_name: str | None = Field(default=None, max_length=200)
    emergency_contact_phone: str | None = None
    emergency_contact_relationship: str | None = Field(default=None, max_length=50)
    preferred_language: str | None = Field(default=None, pattern=LANG)
    spoken_languages: list[str] | None = None
    communication_prefs: dict[str, bool] | None = None

    @field_validator("mobile", "emergency_contact_phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        return normalise_mobile(v) if v else None


class IdentifierOut(BaseModel):
    id: uuid.UUID
    system: str
    masked: str
    verified: bool


class PatientHit(BaseModel):
    """Everything a search result may reveal: enough to pick the right person, no more."""

    id: uuid.UUID
    mrn: str
    full_name: str
    age_years: int | None
    administrative_gender: str
    mobile_masked: str | None


class DuplicateCandidate(PatientHit):
    reasons: list[str]


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mrn: str
    full_name: str
    date_of_birth: date | None
    dob_is_estimated: bool
    age_years: int | None
    administrative_gender: str
    sex_at_birth: str | None
    mobile: str | None
    address: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    emergency_contact_relationship: str | None
    preferred_language: str
    spoken_languages: list[str]
    communication_prefs: dict[str, object]
    identifiers: list[IdentifierOut]
    status: str
    version: int


class RevealedIdentifier(BaseModel):
    id: uuid.UUID
    system: str
    value: str


class TimelineEvent(BaseModel):
    id: uuid.UUID
    event_type: str
    aggregate_type: str
    aggregate_id: uuid.UUID
    occurred_at: str
    actor_user_id: uuid.UUID | None
    payload: dict[str, object]
