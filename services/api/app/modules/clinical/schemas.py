import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ClientSource = Literal["PATIENT_REPORTED", "STAFF_ENTERED", "DOCTOR_ENTERED", "EXTERNAL_RECORD"]
Route = Literal[
    "ORAL",
    "SUBLINGUAL",
    "IV",
    "IM",
    "SC",
    "TOPICAL",
    "INHALED",
    "NASAL",
    "OPHTHALMIC",
    "OTIC",
    "RECTAL",
    "VAGINAL",
    "OTHER",
]


class FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID | None
    source: str
    verification_state: str
    recorded_by: uuid.UUID | None
    recorded_at: datetime
    verified_by: uuid.UUID | None
    verified_at: datetime | None
    rejection_reason: str | None
    supersedes_id: uuid.UUID | None
    is_current: bool


# ---- encounters --------------------------------------------------------------------


class EncounterStart(BaseModel):
    """Which visit to open an encounter for. The URL says whether this is triage or consultation."""

    appointment_id: uuid.UUID


class EncounterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    appointment_id: uuid.UUID
    facility_id: uuid.UUID
    practitioner_id: uuid.UUID | None
    status: str
    triage_category: str | None
    started_at: datetime
    consultation_started_at: datetime | None
    ended_at: datetime | None


class TriageCategoryIn(BaseModel):
    category: Literal["ROUTINE", "URGENT", "EMERGENCY"]


# ---- vitals ------------------------------------------------------------------------


class Measure(BaseModel):
    value: float
    unit: str | None = None


class VitalsIn(BaseModel):
    temperature: Measure | None = None  # unit "C" or "F" (Fahrenheit is common in India)
    systolic_bp: float | None = None
    diastolic_bp: float | None = None
    heart_rate: float | None = None
    respiratory_rate: float | None = None
    spo2: float | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    blood_glucose_mgdl: float | None = None
    glucose_context: Literal["FASTING", "RANDOM", "POST_MEAL"] | None = None
    pain_score: float | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> "VitalsIn":
        if all(getattr(self, f) is None for f in type(self).model_fields if f != "glucose_context"):
            raise ValueError("Enter at least one measurement")
        if (self.systolic_bp is None) != (self.diastolic_bp is None):
            raise ValueError("Enter both systolic and diastolic blood pressure")
        return self


class ObservationOut(FactOut):
    code: str
    value: Decimal
    unit: str
    original_value: Decimal | None
    original_unit: str | None
    context: str | None
    observed_at: datetime
    interpretation: str
    reference_version: str | None


class ObservationCorrection(BaseModel):
    value: float
    unit: str | None = None


# ---- notes -------------------------------------------------------------------------

NoteType = Literal[
    "CHIEF_COMPLAINT",
    "TRIAGE",
    "HPI",
    "PAST_HISTORY",
    "FAMILY_HISTORY",
    "SOCIAL_HISTORY",
    "EXAMINATION",
    "ASSESSMENT",
    "PLAN",
    "GENERAL",
]
TRIAGE_NOTE_TYPES = {"CHIEF_COMPLAINT", "TRIAGE"}


class NoteIn(BaseModel):
    note_type: NoteType
    content: str = Field(min_length=1, max_length=5000)
    source: ClientSource | None = None

    @field_validator("content")
    @classmethod
    def _strip(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Note is empty")
        return v.strip()


class NoteEdit(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class NoteOut(FactOut):
    note_type: str
    content: str


# ---- conditions, allergies, medications ---------------------------------------------


class _Coded(BaseModel):
    code: str | None = Field(default=None, max_length=40)
    code_system: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def _both_or_neither(self) -> "_Coded":
        if (self.code is None) != (self.code_system is None):
            raise ValueError("Provide a code together with its code system")
        return self


class ConditionIn(_Coded):
    display: str = Field(min_length=2, max_length=300)
    category: Literal["DIAGNOSIS", "PROBLEM"] = "DIAGNOSIS"
    certainty: Literal["SUSPECTED", "PROVISIONAL", "CONFIRMED"] = "PROVISIONAL"
    clinical_status: Literal["ACTIVE", "RESOLVED", "INACTIVE"] = "ACTIVE"
    onset_date: date | None = None
    note: str | None = Field(default=None, max_length=500)
    source: ClientSource | None = None


class ConditionEdit(BaseModel):
    display: str | None = Field(default=None, min_length=2, max_length=300)
    certainty: Literal["SUSPECTED", "PROVISIONAL", "CONFIRMED"] | None = None
    clinical_status: Literal["ACTIVE", "RESOLVED", "INACTIVE"] | None = None
    onset_date: date | None = None
    abatement_date: date | None = None
    note: str | None = Field(default=None, max_length=500)


class ConditionOut(FactOut):
    display: str
    code: str | None
    code_system: str | None
    category: str
    clinical_status: str
    certainty: str
    onset_date: date | None
    abatement_date: date | None
    note: str | None


class AllergyIn(_Coded):
    substance: str = Field(default="", max_length=200)
    category: Literal["MEDICATION", "FOOD", "ENVIRONMENT", "OTHER"] = "MEDICATION"
    reaction: str | None = Field(default=None, max_length=300)
    severity: Literal["MILD", "MODERATE", "SEVERE", "UNKNOWN"] = "UNKNOWN"
    certainty: Literal["CONFIRMED", "POSSIBLE", "HISTORICAL"] = "CONFIRMED"
    is_nka: bool = False
    source: ClientSource | None = None

    @model_validator(mode="after")
    def _substance(self) -> "AllergyIn":
        if not self.is_nka and len(self.substance.strip()) < 2:
            raise ValueError("Name the substance")
        return self


class AllergyEdit(BaseModel):
    reaction: str | None = Field(default=None, max_length=300)
    severity: Literal["MILD", "MODERATE", "SEVERE", "UNKNOWN"] | None = None
    certainty: Literal["CONFIRMED", "POSSIBLE", "HISTORICAL"] | None = None
    clinical_status: Literal["ACTIVE", "INACTIVE"] | None = None


class AllergyOut(FactOut):
    substance: str
    substance_code: str | None
    code_system: str | None
    category: str
    reaction: str | None
    severity: str
    certainty: str
    clinical_status: str
    is_nka: bool


class MedicationIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    generic_name: str | None = Field(default=None, max_length=200)
    dose: str | None = Field(default=None, max_length=100)
    route: str | None = Field(default=None, max_length=30)
    frequency: str | None = Field(default=None, max_length=100)
    status: Literal["ACTIVE", "STOPPED"] = "ACTIVE"
    started_on: date | None = None
    source: ClientSource | None = None


class MedicationEdit(BaseModel):
    dose: str | None = Field(default=None, max_length=100)
    route: str | None = Field(default=None, max_length=30)
    frequency: str | None = Field(default=None, max_length=100)
    status: Literal["ACTIVE", "STOPPED"] | None = None
    stopped_on: date | None = None


class MedicationOut(FactOut):
    name: str
    generic_name: str | None
    dose: str | None
    route: str | None
    frequency: str | None
    status: str
    started_on: date | None
    stopped_on: date | None


class VerifyIn(BaseModel):
    action: Literal["confirm", "reject"]
    reason: str | None = Field(default=None, max_length=300)


# ---- prescriptions -----------------------------------------------------------------


class PrescriptionItemIn(BaseModel):
    medicine_name: str = Field(min_length=2, max_length=200)
    generic_name: str | None = Field(default=None, max_length=200)
    brand_name: str | None = Field(default=None, max_length=200)
    strength: str | None = Field(default=None, max_length=60)
    form: str | None = Field(default=None, max_length=40)
    dose: str = Field(min_length=1, max_length=100)
    route: Route
    frequency: str = Field(min_length=1, max_length=100)
    duration_days: int | None = Field(default=None, ge=1, le=730)
    quantity: int | None = Field(default=None, ge=1, le=10000)
    instructions: str | None = Field(default=None, max_length=500)


class PrescriptionItemOut(PrescriptionItemIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    medication_code: str | None = None
    code_system: str | None = None


class PrescriptionIn(BaseModel):
    items: list[PrescriptionItemIn] = Field(min_length=1, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)


class SafetyWarning(BaseModel):
    code: str
    level: Literal["WARNING", "INFO"]
    message: str
    position: int | None = None


class PrescriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID
    practitioner_id: uuid.UUID
    status: str
    notes: str | None
    signed_at: datetime | None
    void_reason: str | None
    items: list[PrescriptionItemOut] = []
    safety_snapshot: dict[str, object] | None = None


class SignIn(BaseModel):
    # Codes of every WARNING the doctor has read and chooses to proceed past.
    acknowledged_warning_codes: list[str] = Field(default_factory=list)


class SafetyCheckOut(BaseModel):
    warnings: list[SafetyWarning]
    checks_not_performed: list[str]


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


# ---- investigations ----------------------------------------------------------------


class ServiceRequestIn(_Coded):
    category: Literal["LAB", "RADIOLOGY", "OTHER"]
    name: str = Field(min_length=2, max_length=200)
    priority: Literal["ROUTINE", "URGENT", "STAT"] = "ROUTINE"
    reason: str | None = Field(default=None, max_length=500)


class ServiceRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID
    category: str
    name: str
    code: str | None
    code_system: str | None
    priority: str
    status: str
    reason: str | None
    source: str
    ordered_at: datetime | None
    cancel_reason: str | None
    patient_name: str | None = None
    patient_mrn: str | None = None


class CancelOrderIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class ResultIn(BaseModel):
    test_name: str = Field(min_length=1, max_length=200)
    value_numeric: Decimal | None = None
    value_text: str | None = Field(default=None, max_length=500)
    unit: str | None = Field(default=None, max_length=30)
    ref_low: Decimal | None = None
    ref_high: Decimal | None = None
    critical_low: Decimal | None = None
    critical_high: Decimal | None = None
    comment: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _has_value(self) -> "ResultIn":
        if self.value_numeric is None and not (self.value_text and self.value_text.strip()):
            raise ValueError("Enter a numeric or text result")
        return self


class ResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    service_request_id: uuid.UUID
    test_name: str
    value_numeric: Decimal | None
    value_text: str | None
    unit: str | None
    ref_low: Decimal | None
    ref_high: Decimal | None
    interpretation: str
    comment: str | None
    reported_at: datetime
    reviewed_at: datetime | None


# ---- follow-up ---------------------------------------------------------------------


class FollowUpIn(BaseModel):
    due_date: date
    kind: Literal["REVIEW", "INVESTIGATION_RESULT", "MEDICATION_REVIEW", "REFERRAL", "OTHER"] = (
        "REVIEW"
    )
    reason: str = Field(min_length=2, max_length=300)

    @field_validator("due_date")
    @classmethod
    def _future(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("Follow-up date cannot be in the past")
        return v


class FollowUpOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID
    due_date: date
    kind: str
    reason: str
    status: str


class FollowUpStatusIn(BaseModel):
    status: Literal["COMPLETED", "CANCELLED"]


# ---- aggregates --------------------------------------------------------------------


class ClinicalAlert(BaseModel):
    level: Literal["CRITICAL", "WARNING", "INFO"]
    code: str
    message: str
    ref_id: uuid.UUID | None = None


class ClinicalState(BaseModel):
    patient_id: uuid.UUID
    allergies: list[AllergyOut]
    allergy_status_recorded: bool
    conditions: list[ConditionOut]
    medications: list[MedicationOut]
    latest_vitals: list[ObservationOut]
    bmi: float | None
    recent_encounters: list[EncounterOut]
    results_awaiting_review: list[ResultOut]
    alerts: list[ClinicalAlert]
    generated_at: datetime


class EncounterDetail(BaseModel):
    encounter: EncounterOut
    notes: list[NoteOut]
    vitals: list[ObservationOut]
    conditions: list[ConditionOut]
    prescriptions: list[PrescriptionOut]
    orders: list[ServiceRequestOut]
    follow_ups: list[FollowUpOut]
