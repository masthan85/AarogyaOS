import uuid
from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WorkingHoursIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def _order(self) -> "WorkingHoursIn":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class PractitionerCreate(BaseModel):
    user_id: uuid.UUID
    facility_id: uuid.UUID
    department_id: uuid.UUID | None = None
    specialty: str = Field(min_length=2, max_length=100)
    registration_number: str | None = Field(default=None, max_length=50)
    consultation_minutes: int = Field(default=15, ge=5, le=120)


class PractitionerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str = ""
    facility_id: uuid.UUID
    department_id: uuid.UUID | None
    specialty: str
    registration_number: str | None
    consultation_minutes: int
    status: str
    working_hours: list[WorkingHoursIn] = []


class WorkingHoursUpdate(BaseModel):
    hours: list[WorkingHoursIn] = Field(max_length=28)


class SlotOut(BaseModel):
    start_at: datetime
    end_at: datetime


class _Aware(BaseModel):
    @field_validator("start_at", check_fields=False)
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("start_at must include a timezone offset")
        return v


class AppointmentCreate(_Aware):
    patient_id: uuid.UUID
    practitioner_id: uuid.UUID
    start_at: datetime
    reason: str | None = Field(default=None, max_length=300)


class RescheduleRequest(_Aware):
    start_at: datetime


class CancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class CheckInRequest(BaseModel):
    priority: Literal["ROUTINE", "URGENT"] = "ROUTINE"


class WalkInCreate(BaseModel):
    patient_id: uuid.UUID
    facility_id: uuid.UUID
    practitioner_id: uuid.UUID | None = None
    reason: str | None = Field(default=None, max_length=300)
    priority: Literal["ROUTINE", "URGENT"] = "ROUTINE"


class AppointmentOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str
    patient_mrn: str
    practitioner_id: uuid.UUID | None
    practitioner_name: str | None
    facility_id: uuid.UUID
    kind: str
    status: str
    start_at: datetime
    end_at: datetime
    reason: str | None
    token_number: int | None
    priority: str | None


class QueueItem(BaseModel):
    appointment_id: uuid.UUID
    token_number: int
    priority: str
    status: str
    patient_id: uuid.UUID
    patient_name: str
    patient_mrn: str
    age_years: int | None
    administrative_gender: str
    practitioner_id: uuid.UUID | None
    practitioner_name: str | None
    waiting_since: datetime
    # None = not yet triaged; TRIAGE / IN_PROGRESS / COMPLETED once an encounter exists.
    encounter_status: str | None = None
