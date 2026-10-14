import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, new_uuid


class MrnCounter(Base):
    __tablename__ = "mrn_counters"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id"), primary_key=True
    )
    last_value: Mapped[int] = mapped_column(Integer, default=0)


class Patient(Base, TimestampMixin):
    __tablename__ = "patients"
    __table_args__ = (
        Index("uq_patients_org_mrn", "organisation_id", "mrn", unique=True),
        Index("ix_patients_org_mobile", "organisation_id", "mobile"),
        Index("ix_patients_org_dob", "organisation_id", "date_of_birth"),
        Index(
            "ix_patients_name_trgm",
            "normalised_name",
            postgresql_using="gin",
            postgresql_ops={"normalised_name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    mrn: Mapped[str] = mapped_column(String(20))
    full_name: Mapped[str] = mapped_column(String(200))
    normalised_name: Mapped[str] = mapped_column(String(200))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    dob_is_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    administrative_gender: Mapped[str] = mapped_column(String(10), default="unknown")
    sex_at_birth: Mapped[str | None] = mapped_column(String(10))
    # E.164. NOT unique: Indian families commonly share one mobile number.
    mobile: Mapped[str | None] = mapped_column(String(16))
    address: Mapped[str | None] = mapped_column(String(500))
    emergency_contact_name: Mapped[str | None] = mapped_column(String(200))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(16))
    emergency_contact_relationship: Mapped[str | None] = mapped_column(String(50))
    preferred_language: Mapped[str] = mapped_column(String(35), default="en-IN")
    communication_prefs: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID | None] = mapped_column()


class PatientIdentifier(Base):
    __tablename__ = "patient_identifiers"
    __table_args__ = (
        Index(
            "uq_patient_identifiers_lookup", "organisation_id", "system", "value_index", unique=True
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), index=True)
    system: Mapped[str] = mapped_column(String(20))
    value_ciphertext: Mapped[str] = mapped_column(String(500))
    value_index: Mapped[str] = mapped_column(String(64))
    display_hint: Mapped[str] = mapped_column(String(40))
    # True only after verification with the issuing authority (ABDM adapter, Phase 6).
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PatientLanguage(Base):
    __tablename__ = "patient_languages"

    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), primary_key=True)
    language_tag: Mapped[str] = mapped_column(String(35), primary_key=True)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))


class PatientRevision(Base):
    """Previous values of changed demographics: nothing is overwritten silently."""

    __tablename__ = "patient_revisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    previous_values: Mapped[dict[str, object]] = mapped_column(JSONB)
    changed_by: Mapped[uuid.UUID | None] = mapped_column()
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
