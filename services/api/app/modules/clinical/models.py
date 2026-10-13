"""Clinical record tables.

Every clinically meaningful *fact* (vitals, notes, conditions, allergies, medication history)
carries provenance (`source`), a verification state, and a supersedes chain. Facts are never
edited in place: a correction inserts a new row and flips `is_current` on the old one. The
content of the old row is untouched, so history is always reconstructable.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, new_uuid

SOURCES = (
    "PATIENT_REPORTED",
    "STAFF_ENTERED",
    "DOCTOR_ENTERED",
    "DEVICE_RECORDED",
    "LAB_RESULT",
    "EXTERNAL_RECORD",
    "AI_EXTRACTED",
)
VERIFICATION_STATES = (
    "UNVERIFIED",
    "AI_GENERATED",
    "REQUIRES_REVIEW",
    "CLINICIAN_CONFIRMED",
    "CLINICIAN_EDITED",
    "CLINICIAN_REJECTED",
)


class FactMixin:
    """Provenance columns shared by all clinical facts."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"))
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("encounters.id"))
    source: Mapped[str] = mapped_column(String(20))
    verification_state: Mapped[str] = mapped_column(String(20), default="UNVERIFIED")
    recorded_by: Mapped[uuid.UUID | None] = mapped_column()
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column()
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(300))
    # Transcript segments this fact was derived from (populated by the AI pipeline, Phase 5).
    evidence_segment_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column()
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)


class Encounter(Base, TimestampMixin):
    __tablename__ = "encounters"
    __table_args__ = (Index("ix_encounters_patient_started", "patient_id", "started_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"))
    facility_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facilities.id"))
    practitioner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("practitioners.id"))
    # Every encounter belongs to a visit; one encounter per appointment.
    appointment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments.id"), unique=True)
    status: Mapped[str] = mapped_column(
        String(15), default="TRIAGE"
    )  # TRIAGE|IN_PROGRESS|COMPLETED
    # Nurse's urgency judgement; never computed by software.
    triage_category: Mapped[str | None] = mapped_column(String(15))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consultation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column()


class Observation(Base, FactMixin):
    __tablename__ = "observations"
    __table_args__ = (Index("ix_observations_patient_code", "patient_id", "code", "is_current"),)

    code: Mapped[str] = mapped_column(String(30))  # TEMPERATURE_C, HEART_RATE, ...
    value: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # canonical unit
    unit: Mapped[str] = mapped_column(String(15))
    original_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    original_unit: Mapped[str | None] = mapped_column(String(15))
    context: Mapped[str | None] = mapped_column(String(20))  # e.g. glucose FASTING / RANDOM
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Deterministic reading against a versioned reference table; never LLM-derived.
    interpretation: Mapped[str] = mapped_column(String(15), default="UNKNOWN")
    reference_version: Mapped[str | None] = mapped_column(String(30))


class ClinicalNote(Base, FactMixin):
    __tablename__ = "clinical_notes"
    __table_args__ = (Index("ix_clinical_notes_encounter", "encounter_id", "is_current"),)

    note_type: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)


class Condition(Base, FactMixin):
    __tablename__ = "conditions"
    __table_args__ = (Index("ix_conditions_patient", "patient_id", "is_current"),)

    display: Mapped[str] = mapped_column(String(300))
    # Codes come from a terminology service (SNOMED CT / ICD) when one is connected; never invented.
    code: Mapped[str | None] = mapped_column(String(40))
    code_system: Mapped[str | None] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(20), default="DIAGNOSIS")  # DIAGNOSIS | PROBLEM
    clinical_status: Mapped[str] = mapped_column(String(10), default="ACTIVE")
    certainty: Mapped[str] = mapped_column(String(12), default="PROVISIONAL")
    onset_date: Mapped[date | None] = mapped_column(Date)
    abatement_date: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(500))


class Allergy(Base, FactMixin):
    __tablename__ = "allergies"
    __table_args__ = (Index("ix_allergies_patient", "patient_id", "is_current"),)

    substance: Mapped[str] = mapped_column(String(200))
    substance_code: Mapped[str | None] = mapped_column(String(40))
    code_system: Mapped[str | None] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(15), default="MEDICATION")
    reaction: Mapped[str | None] = mapped_column(String(300))
    severity: Mapped[str] = mapped_column(String(10), default="UNKNOWN")
    # POSSIBLE covers "I might have been allergic as a child": kept, never treated as confirmed.
    certainty: Mapped[str] = mapped_column(String(12), default="CONFIRMED")
    clinical_status: Mapped[str] = mapped_column(String(10), default="ACTIVE")
    is_nka: Mapped[bool] = mapped_column(Boolean, default=False)  # "no known allergies" statement


class PatientMedication(Base, FactMixin):
    """What the patient takes (history), distinct from what a doctor prescribes today."""

    __tablename__ = "patient_medications"
    __table_args__ = (Index("ix_patient_medications_patient", "patient_id", "is_current"),)

    name: Mapped[str] = mapped_column(String(200))
    generic_name: Mapped[str | None] = mapped_column(String(200))
    dose: Mapped[str | None] = mapped_column(String(100))
    route: Mapped[str | None] = mapped_column(String(30))
    frequency: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")
    started_on: Mapped[date | None] = mapped_column(Date)
    stopped_on: Mapped[date | None] = mapped_column(Date)


class Prescription(Base, TimestampMixin):
    __tablename__ = "prescriptions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), index=True)
    practitioner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("practitioners.id"))
    status: Mapped[str] = mapped_column(String(10), default="DRAFT")  # DRAFT | SIGNED | VOIDED
    notes: Mapped[str | None] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(20), default="DOCTOR_ENTERED")
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_by: Mapped[uuid.UUID | None] = mapped_column()
    # Warnings the doctor saw and acknowledged at signing, and which checks could not run.
    safety_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    void_reason: Mapped[str | None] = mapped_column(String(300))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[uuid.UUID | None] = mapped_column()
    created_by: Mapped[uuid.UUID | None] = mapped_column()


class PrescriptionItem(Base):
    __tablename__ = "prescription_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    prescription_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prescriptions.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    medicine_name: Mapped[str] = mapped_column(String(200))
    generic_name: Mapped[str | None] = mapped_column(String(200))
    brand_name: Mapped[str | None] = mapped_column(String(200))
    strength: Mapped[str | None] = mapped_column(String(60))
    form: Mapped[str | None] = mapped_column(String(40))
    dose: Mapped[str] = mapped_column(String(100))
    route: Mapped[str] = mapped_column(String(30))
    frequency: Mapped[str] = mapped_column(String(100))
    duration_days: Mapped[int | None] = mapped_column(Integer)
    quantity: Mapped[int | None] = mapped_column(Integer)
    instructions: Mapped[str | None] = mapped_column(String(500))
    # Filled from a licensed medication database once connected; never invented.
    medication_code: Mapped[str | None] = mapped_column(String(40))
    code_system: Mapped[str | None] = mapped_column(String(40))


class ServiceRequest(Base, TimestampMixin):
    __tablename__ = "service_requests"
    __table_args__ = (Index("ix_service_requests_queue", "organisation_id", "category", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), index=True)
    category: Mapped[str] = mapped_column(String(10))  # LAB | RADIOLOGY | OTHER
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str | None] = mapped_column(String(40))  # LOINC etc. via terminology service
    code_system: Mapped[str | None] = mapped_column(String(40))
    priority: Mapped[str] = mapped_column(String(10), default="ROUTINE")
    status: Mapped[str] = mapped_column(
        String(10), default="DRAFT"
    )  # DRAFT|ORDERED|CANCELLED|RESULTED
    reason: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(20), default="DOCTOR_ENTERED")
    ordered_by: Mapped[uuid.UUID | None] = mapped_column()
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID | None] = mapped_column()


class InvestigationResult(Base):
    __tablename__ = "investigation_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), index=True)
    service_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_requests.id"), index=True
    )
    test_name: Mapped[str] = mapped_column(String(200))
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    value_text: Mapped[str | None] = mapped_column(String(500))
    unit: Mapped[str | None] = mapped_column(String(30))
    # Reference range supplied by the reporting laboratory (ranges vary by method and lab).
    ref_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    ref_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    critical_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    critical_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    interpretation: Mapped[str] = mapped_column(String(15), default="UNKNOWN")
    comment: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(20), default="LAB_RESULT")
    reported_by: Mapped[uuid.UUID | None] = mapped_column()
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column()
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FollowUp(Base, TimestampMixin):
    __tablename__ = "follow_ups"
    __table_args__ = (Index("ix_follow_ups_due", "organisation_id", "status", "due_date"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"))
    due_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20), default="REVIEW")
    reason: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(10), default="PENDING")
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
