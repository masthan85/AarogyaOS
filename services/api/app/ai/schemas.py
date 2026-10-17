"""The only shapes model output is allowed to take. Anything else is rejected, not repaired."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Kind = Literal[
    "CHIEF_COMPLAINT",
    "SYMPTOM",
    "MEDICAL_HISTORY",
    "SURGICAL_HISTORY",
    "FAMILY_HISTORY",
    "SOCIAL_HISTORY",
    "MEDICATION",
    "ALLERGY",
    "PREVIOUS_TREATMENT",
    "EXAMINATION_FINDING",
    "VITAL_MENTIONED",
    "DIAGNOSIS_DISCUSSED",
    "INVESTIGATION_DISCUSSED",
    "TREATMENT_DISCUSSED",
    "FOLLOW_UP",
    "CIRCUMSTANCE",
]
Assertion = Literal["PRESENT", "ABSENT", "POSSIBLE", "HISTORICAL"]
Subject = Literal["PATIENT", "FAMILY_MEMBER", "OTHER"]

ALL_KINDS: tuple[str, ...] = Kind.__args__  # type: ignore[attr-defined]

# Which kinds each recording purpose may produce. A reception conversation is administrative:
# it must not create symptoms, histories, medicines or diagnoses.
KINDS_BY_PURPOSE: dict[str, frozenset[str]] = {
    "RECEPTION": frozenset({"CHIEF_COMPLAINT", "FOLLOW_UP"}),
    "TRIAGE": frozenset(ALL_KINDS)
    - {"DIAGNOSIS_DISCUSSED", "TREATMENT_DISCUSSED", "INVESTIGATION_DISCUSSED"},
    "CONSULTATION": frozenset(ALL_KINDS),
}

# Attribute keys a candidate may carry. Unknown keys are discarded, not trusted.
ALLOWED_ATTRIBUTES: dict[str, frozenset[str]] = {
    "SYMPTOM": frozenset(
        {"duration", "onset", "severity", "site", "pattern", "trigger", "relieved_by"}
    ),
    "CHIEF_COMPLAINT": frozenset({"duration", "onset", "severity", "site"}),
    "ALLERGY": frozenset({"substance", "reaction", "severity", "when"}),
    "MEDICATION": frozenset({"medicine", "dose", "route", "frequency", "duration", "adherence"}),
    "TREATMENT_DISCUSSED": frozenset({"medicine", "dose", "route", "frequency", "duration"}),
    "INVESTIGATION_DISCUSSED": frozenset({"test", "category"}),
    "VITAL_MENTIONED": frozenset({"measure", "value", "unit"}),
    "EXAMINATION_FINDING": frozenset({"site", "finding"}),
    "MEDICAL_HISTORY": frozenset({"condition", "duration", "when"}),
    "SURGICAL_HISTORY": frozenset({"procedure", "when"}),
    "FAMILY_HISTORY": frozenset({"condition", "relative"}),
    "SOCIAL_HISTORY": frozenset({"topic", "detail"}),
    "PREVIOUS_TREATMENT": frozenset({"treatment", "outcome", "when"}),
    "DIAGNOSIS_DISCUSSED": frozenset({"diagnosis"}),
    "FOLLOW_UP": frozenset({"when", "reason"}),
    # What led to the problem: an injury, a fall, lifting, an event, with when it happened.
    "CIRCUMSTANCE": frozenset({"event", "mechanism", "when"}),
}


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=1)
    quote: str = Field(min_length=2, max_length=400)


class RawCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Kind
    text: str = Field(min_length=1, max_length=300)  # normalised clinical wording, in English
    assertion: Assertion
    subject: Subject = "PATIENT"
    attributes: dict[str, str] = Field(default_factory=dict)
    original_term: str | None = Field(default=None, max_length=120)
    evidence: list[Evidence] = Field(min_length=1, max_length=3)

    @field_validator("attributes")
    @classmethod
    def _bounded(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 8 or any(len(str(x)) > 120 for x in v.values()):
            raise ValueError("attributes too large")
        return {str(k): str(x) for k, x in v.items()}


class ExtractionEnvelope(BaseModel):
    """Top level: candidates are validated one by one so one bad item doesn't discard the rest."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[dict[str, object]] = Field(max_length=60)


class SuggestionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "IMPORTANT_INFORMATION",
        "MISSING_HISTORY_QUESTION",
        "DIFFERENTIAL",
        "INVESTIGATION",
        "MEDICATION_CONSIDERATION",
        "INTERACTION",
        "CONTRAINDICATION",
        "ALLERGY_WARNING",
        "PREVIOUS_INFORMATION",
        "ABNORMAL_RESULT",
        "GUIDELINE",
        "REFERRAL",
        "FOLLOW_UP",
        "PATIENT_EDUCATION",
    ]
    title: str = Field(min_length=3, max_length=160)
    explanation: str = Field(min_length=3, max_length=800)
    uncertainty: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    uncertainty_note: str | None = Field(default=None, max_length=300)
    # Ids the model was shown (candidate / fact / segment refs) that this relies on.
    supporting_refs: list[str] = Field(default_factory=list, max_length=10)
    # Ids of retrieved knowledge chunks it cites.
    source_chunk_ids: list[str] = Field(default_factory=list, max_length=5)
    medicine_name: str | None = Field(default=None, max_length=120)
    test_name: str | None = Field(default=None, max_length=160)
    test_category: Literal["LAB", "RADIOLOGY", "OTHER"] | None = None


class SuggestionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestions: list[dict[str, object]] = Field(max_length=20)
