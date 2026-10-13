import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, new_uuid

ACTIVE_STATUSES = ("BOOKED", "CONFIRMED", "ARRIVED", "CHECKED_IN", "WAITING", "IN_CONSULTATION")


class Practitioner(Base, TimestampMixin):
    __tablename__ = "practitioners"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    facility_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facilities.id"), index=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    specialty: Mapped[str] = mapped_column(String(100))
    # Recorded for display. Registration is NOT verified against NMC/state registers yet.
    registration_number: Mapped[str | None] = mapped_column(String(50))
    consultation_minutes: Mapped[int] = mapped_column(Integer, default=15)
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")


class WorkingHours(Base):
    __tablename__ = "working_hours"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    practitioner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("practitioners.id"), index=True)
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 0 = Monday
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)


class Appointment(Base, TimestampMixin):
    __tablename__ = "appointments"
    __table_args__ = (
        Index("ix_appointments_org_start", "organisation_id", "start_at"),
        Index("ix_appointments_practitioner_start", "practitioner_id", "start_at"),
        # The no-overlap EXCLUDE constraint lives in the migration (SQLAlchemy can't
        # autogenerate it): one practitioner cannot hold two overlapping scheduled slots.
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), index=True)
    practitioner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("practitioners.id"))
    facility_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facilities.id"))
    kind: Mapped[str] = mapped_column(String(10), default="SCHEDULED")  # SCHEDULED | WALK_IN
    status: Mapped[str] = mapped_column(String(20), default="BOOKED")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(300))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    booked_by: Mapped[uuid.UUID | None] = mapped_column()
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QueueCounter(Base):
    __tablename__ = "queue_counters"

    facility_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facilities.id"), primary_key=True)
    token_date: Mapped[date] = mapped_column(Date, primary_key=True)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    last_value: Mapped[int] = mapped_column(Integer, default=0)


class QueueEntry(Base):
    __tablename__ = "queue_entries"
    __table_args__ = (
        Index("uq_queue_token", "facility_id", "token_date", "token_number", unique=True),
        Index("ix_queue_facility_date", "facility_id", "token_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    facility_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facilities.id"))
    appointment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments.id"), unique=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"))
    practitioner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("practitioners.id"))
    token_date: Mapped[date] = mapped_column(Date)
    token_number: Mapped[int] = mapped_column(Integer)
    priority: Mapped[str] = mapped_column(String(10), default="ROUTINE")  # ROUTINE | URGENT
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
