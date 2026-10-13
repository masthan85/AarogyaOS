import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import AppError, Conflict, NotFound
from app.modules.audit.service import emit_event, record_audit
from app.modules.identity.models import Role, User, UserRole
from app.modules.patients.models import Patient
from app.modules.patients.normalise import age_years
from app.modules.scheduling.models import (
    ACTIVE_STATUSES,
    Appointment,
    Practitioner,
    QueueCounter,
    QueueEntry,
    WorkingHours,
)
from app.modules.scheduling.schemas import (
    AppointmentCreate,
    AppointmentOut,
    PractitionerCreate,
    PractitionerOut,
    QueueItem,
    SlotOut,
    WalkInCreate,
    WorkingHoursIn,
)
from app.modules.tenancy.models import Facility

# Appointment lifecycle. Anything not listed is refused, whoever asks.
TRANSITIONS: dict[str, set[str]] = {
    "BOOKED": {"CONFIRMED", "ARRIVED", "CHECKED_IN", "WAITING", "CANCELLED", "NO_SHOW"},
    "CONFIRMED": {"ARRIVED", "CHECKED_IN", "WAITING", "CANCELLED", "NO_SHOW"},
    "ARRIVED": {"CHECKED_IN", "WAITING", "CANCELLED"},
    "CHECKED_IN": {"WAITING", "IN_CONSULTATION", "CANCELLED"},
    "WAITING": {"IN_CONSULTATION", "CANCELLED"},
    "IN_CONSULTATION": {"COMPLETED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
    "NO_SHOW": set(),
}
CHECK_IN_FROM = {"BOOKED", "CONFIRMED", "ARRIVED"}


def _org(principal: Principal) -> uuid.UUID:
    assert principal.org_id is not None
    return principal.org_id


def _now() -> datetime:
    return datetime.now(UTC)


# ---- practitioners ---------------------------------------------------------------


def _practitioner_out(session: Session, p: Practitioner) -> PractitionerOut:
    name = session.scalar(select(User.full_name).where(User.id == p.user_id)) or ""
    hours = session.scalars(
        select(WorkingHours)
        .where(WorkingHours.practitioner_id == p.id)
        .order_by(WorkingHours.weekday, WorkingHours.start_time)
    ).all()
    out = PractitionerOut.model_validate(p)
    out.full_name = name
    out.working_hours = [
        WorkingHoursIn(weekday=h.weekday, start_time=h.start_time, end_time=h.end_time)
        for h in hours
    ]
    return out


def create_practitioner(
    session: Session, principal: Principal, body: PractitionerCreate
) -> PractitionerOut:
    org_id = _org(principal)
    is_doctor = session.scalar(
        select(UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == body.user_id, Role.key == "doctor")
    )
    if not is_doctor:
        raise AppError("The user must exist in this organisation and hold the doctor role")
    if session.get(Facility, body.facility_id) is None:
        raise NotFound("Facility not found")
    practitioner = Practitioner(organisation_id=org_id, **body.model_dump())
    session.add(practitioner)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise Conflict("This user already has a practitioner profile") from exc
    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action="PRACTITIONER_CREATED",
        resource_type="practitioner",
        resource_id=practitioner.id,
    )
    session.commit()
    return _practitioner_out(session, practitioner)


def _get_practitioner(session: Session, practitioner_id: uuid.UUID) -> Practitioner:
    p = session.get(Practitioner, practitioner_id)
    if p is None:
        raise NotFound("Practitioner not found")
    return p


def list_practitioners(
    session: Session, facility_id: uuid.UUID | None, specialty: str | None
) -> list[PractitionerOut]:
    stmt = select(Practitioner).where(Practitioner.status == "ACTIVE")
    if facility_id:
        stmt = stmt.where(Practitioner.facility_id == facility_id)
    if specialty:
        stmt = stmt.where(Practitioner.specialty.ilike(f"%{specialty.strip()}%"))
    return [
        _practitioner_out(session, p)
        for p in session.scalars(stmt.order_by(Practitioner.specialty))
    ]


def set_working_hours(
    session: Session, principal: Principal, practitioner_id: uuid.UUID, hours: list[WorkingHoursIn]
) -> PractitionerOut:
    p = _get_practitioner(session, practitioner_id)
    by_day: dict[int, list[WorkingHoursIn]] = {}
    for h in hours:
        by_day.setdefault(h.weekday, []).append(h)
    for blocks in by_day.values():
        blocks.sort(key=lambda b: b.start_time)
        for a, b in zip(blocks, blocks[1:], strict=False):
            if b.start_time < a.end_time:
                raise AppError("Working hours on the same day must not overlap")
    session.execute(delete(WorkingHours).where(WorkingHours.practitioner_id == p.id))
    for h in hours:
        session.add(
            WorkingHours(
                organisation_id=_org(principal),
                practitioner_id=p.id,
                weekday=h.weekday,
                start_time=h.start_time,
                end_time=h.end_time,
            )
        )
    record_audit(
        session,
        principal.meta,
        org_id=_org(principal),
        actor_user_id=principal.user_id,
        action="WORKING_HOURS_SET",
        resource_type="practitioner",
        resource_id=p.id,
    )
    session.commit()
    return _practitioner_out(session, p)


def _facility_tz(session: Session, facility_id: uuid.UUID) -> ZoneInfo:
    facility = session.get(Facility, facility_id)
    if facility is None:
        raise NotFound("Facility not found")
    return ZoneInfo(facility.timezone)


def _local_day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=tz)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def _free_slots(session: Session, p: Practitioner, day: date) -> list[SlotOut]:
    tz = _facility_tz(session, p.facility_id)
    hours = session.scalars(
        select(WorkingHours).where(
            WorkingHours.practitioner_id == p.id, WorkingHours.weekday == day.weekday()
        )
    ).all()
    lo, hi = _local_day_bounds(day, tz)
    taken = session.execute(
        select(Appointment.start_at, Appointment.end_at).where(
            Appointment.practitioner_id == p.id,
            Appointment.kind == "SCHEDULED",
            Appointment.status.in_(ACTIVE_STATUSES),
            Appointment.start_at < hi,
            Appointment.end_at > lo,
        )
    ).all()
    step = timedelta(minutes=p.consultation_minutes)
    now = _now()
    slots: list[SlotOut] = []
    for block in sorted(hours, key=lambda b: b.start_time):
        cursor = datetime.combine(day, block.start_time, tzinfo=tz)
        end = datetime.combine(day, block.end_time, tzinfo=tz)
        while cursor + step <= end:
            s, e = cursor.astimezone(UTC), (cursor + step).astimezone(UTC)
            if s > now and not any(s < t_end and e > t_start for t_start, t_end in taken):
                slots.append(SlotOut(start_at=s, end_at=e))
            cursor += step
    return slots


def available_slots(session: Session, practitioner_id: uuid.UUID, day: date) -> list[SlotOut]:
    return _free_slots(session, _get_practitioner(session, practitioner_id), day)


# ---- appointments ----------------------------------------------------------------


def _base_query() -> Any:
    return (
        select(
            Appointment,
            Patient.full_name,
            Patient.mrn,
            User.full_name,
            QueueEntry.token_number,
            QueueEntry.priority,
        )
        .join(Patient, Patient.id == Appointment.patient_id)
        .outerjoin(Practitioner, Practitioner.id == Appointment.practitioner_id)
        .outerjoin(User, User.id == Practitioner.user_id)
        .outerjoin(QueueEntry, QueueEntry.appointment_id == Appointment.id)
    )


def _to_out(
    row: tuple[Appointment, str, str, str | None, int | None, str | None],
) -> AppointmentOut:
    a, pname, mrn, dname, token, prio = row
    return AppointmentOut(
        id=a.id,
        patient_id=a.patient_id,
        patient_name=pname,
        patient_mrn=mrn,
        practitioner_id=a.practitioner_id,
        practitioner_name=dname,
        facility_id=a.facility_id,
        kind=a.kind,
        status=a.status,
        start_at=a.start_at,
        end_at=a.end_at,
        reason=a.reason,
        token_number=token,
        priority=prio,
    )


def _appointment_out(session: Session, appointment_id: uuid.UUID) -> AppointmentOut:
    row = session.execute(_base_query().where(Appointment.id == appointment_id)).first()
    if row is None:
        raise NotFound("Appointment not found")
    return _to_out(tuple(row))


def _lock_appointment(session: Session, appointment_id: uuid.UUID) -> Appointment:
    a = session.scalar(
        select(Appointment).where(Appointment.id == appointment_id).with_for_update()
    )
    if a is None:
        raise NotFound("Appointment not found")
    return a


def _require_slot(session: Session, p: Practitioner, start: datetime) -> datetime:
    start = start.astimezone(UTC)
    tz = _facility_tz(session, p.facility_id)
    day = start.astimezone(tz).date()
    if start not in {s.start_at for s in _free_slots(session, p, day)}:
        raise Conflict("That time is not an available slot for this doctor")
    return start + timedelta(minutes=p.consultation_minutes)


def book(session: Session, principal: Principal, body: AppointmentCreate) -> AppointmentOut:
    org_id = _org(principal)
    patient = session.get(Patient, body.patient_id)
    if patient is None or patient.status != "ACTIVE":
        raise NotFound("Patient not found")
    p = _get_practitioner(session, body.practitioner_id)
    if p.status != "ACTIVE":
        raise AppError("This practitioner is not taking appointments")
    end = _require_slot(session, p, body.start_at)
    start = body.start_at.astimezone(UTC)
    clash = session.scalar(
        select(Appointment.id).where(
            Appointment.patient_id == patient.id,
            Appointment.kind == "SCHEDULED",
            Appointment.status.in_(ACTIVE_STATUSES),
            Appointment.start_at < end,
            Appointment.end_at > start,
        )
    )
    if clash:
        raise Conflict("The patient already has an appointment at this time")
    appt = Appointment(
        organisation_id=org_id,
        patient_id=patient.id,
        practitioner_id=p.id,
        facility_id=p.facility_id,
        start_at=start,
        end_at=end,
        reason=body.reason,
        booked_by=principal.user_id,
    )
    try:
        with session.begin_nested():
            session.add(appt)
            session.flush()
    except IntegrityError as exc:  # the exclusion constraint: someone else won the race
        raise Conflict("That slot was just taken. Pick another time.") from exc
    _event(session, principal, "APPOINTMENT_BOOKED", appt, {"practitioner_id": str(p.id)})
    session.commit()
    return _appointment_out(session, appt.id)


def _event(
    session: Session,
    principal: Principal,
    event_type: str,
    appt: Appointment,
    payload: dict[str, object] | None = None,
) -> None:
    org_id = _org(principal)
    emit_event(
        session,
        org_id=org_id,
        event_type=event_type,
        aggregate_type="appointment",
        aggregate_id=appt.id,
        patient_id=appt.patient_id,
        actor_user_id=principal.user_id,
        payload=payload,
    )
    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action=event_type,
        resource_type="appointment",
        resource_id=appt.id,
    )


def _move(session: Session, principal: Principal, appt: Appointment, to: str, event: str) -> None:
    if to not in TRANSITIONS[appt.status]:
        was, wanted = (x.lower().replace("_", " ") for x in (appt.status, to))
        raise Conflict(f"An appointment that is {was} cannot be {wanted}")
    previous = appt.status
    appt.status = to
    _event(session, principal, event, appt, {"from": previous, "to": to})


def reschedule(
    session: Session, principal: Principal, appointment_id: uuid.UUID, start_at: datetime
) -> AppointmentOut:
    appt = _lock_appointment(session, appointment_id)
    if (
        appt.status not in {"BOOKED", "CONFIRMED"}
        or appt.kind != "SCHEDULED"
        or not appt.practitioner_id
    ):
        raise Conflict("Only upcoming scheduled appointments can be rescheduled")
    p = _get_practitioner(session, appt.practitioner_id)
    end = _require_slot(session, p, start_at)
    old = appt.start_at
    appt.start_at, appt.end_at = start_at.astimezone(UTC), end
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as exc:
        raise Conflict("That slot was just taken. Pick another time.") from exc
    _event(session, principal, "APPOINTMENT_RESCHEDULED", appt, {"from": old.isoformat()})
    session.commit()
    return _appointment_out(session, appt.id)


def cancel(
    session: Session, principal: Principal, appointment_id: uuid.UUID, reason: str | None
) -> AppointmentOut:
    appt = _lock_appointment(session, appointment_id)
    appt.cancel_reason = reason
    _move(session, principal, appt, "CANCELLED", "APPOINTMENT_CANCELLED")
    session.commit()
    return _appointment_out(session, appt.id)


def set_simple_status(
    session: Session, principal: Principal, appointment_id: uuid.UUID, to: str
) -> AppointmentOut:
    appt = _lock_appointment(session, appointment_id)
    _move(session, principal, appt, to, "APPOINTMENT_STATUS_CHANGED")
    if to == "IN_CONSULTATION":
        if appt.practitioner_id:
            busy = session.scalar(
                select(Appointment.id).where(
                    Appointment.practitioner_id == appt.practitioner_id,
                    Appointment.status == "IN_CONSULTATION",
                    Appointment.id != appt.id,
                )
            )
            if busy:
                raise Conflict("This doctor is still with another patient")
        _stamp_queue(session, appt.id, called=True)
    elif to == "COMPLETED":
        _stamp_queue(session, appt.id, completed=True)
    session.commit()
    return _appointment_out(session, appt.id)


def _stamp_queue(
    session: Session, appointment_id: uuid.UUID, *, called: bool = False, completed: bool = False
) -> None:
    entry = session.scalar(select(QueueEntry).where(QueueEntry.appointment_id == appointment_id))
    if entry:
        if called:
            entry.called_at = _now()
        if completed:
            entry.completed_at = _now()


def list_appointments(
    session: Session,
    *,
    day: date | None,
    practitioner_id: uuid.UUID | None,
    facility_id: uuid.UUID | None,
    patient_id: uuid.UUID | None,
    status: str | None,
    limit: int,
    offset: int,
) -> list[AppointmentOut]:
    stmt = _base_query()
    if day:
        tz = _facility_tz(session, facility_id) if facility_id else ZoneInfo("Asia/Kolkata")
        lo, hi = _local_day_bounds(day, tz)
        stmt = stmt.where(Appointment.start_at >= lo, Appointment.start_at < hi)
    if practitioner_id:
        stmt = stmt.where(Appointment.practitioner_id == practitioner_id)
    if facility_id:
        stmt = stmt.where(Appointment.facility_id == facility_id)
    if patient_id:
        stmt = stmt.where(Appointment.patient_id == patient_id)
    if status:
        stmt = stmt.where(Appointment.status == status)
    rows = session.execute(stmt.order_by(Appointment.start_at).limit(limit).offset(offset)).all()
    return [_to_out(tuple(r)) for r in rows]


# ---- check-in, walk-ins, queue ---------------------------------------------------


def _issue_token(session: Session, appt: Appointment, priority: str) -> QueueEntry:
    tz = _facility_tz(session, appt.facility_id)
    today = _now().astimezone(tz).date()
    stmt = (
        pg_insert(QueueCounter)
        .values(
            facility_id=appt.facility_id,
            token_date=today,
            organisation_id=appt.organisation_id,
            last_value=1,
        )
        .on_conflict_do_update(
            index_elements=[QueueCounter.facility_id, QueueCounter.token_date],
            set_={"last_value": QueueCounter.last_value + 1},
        )
        .returning(QueueCounter.last_value)
    )
    number = session.execute(stmt).scalar_one()
    entry = QueueEntry(
        organisation_id=appt.organisation_id,
        facility_id=appt.facility_id,
        appointment_id=appt.id,
        patient_id=appt.patient_id,
        practitioner_id=appt.practitioner_id,
        token_date=today,
        token_number=number,
        priority=priority,
    )
    session.add(entry)
    session.flush()
    return entry


def check_in(
    session: Session, principal: Principal, appointment_id: uuid.UUID, priority: str
) -> AppointmentOut:
    appt = _lock_appointment(session, appointment_id)
    if appt.status not in CHECK_IN_FROM:
        raise Conflict("This appointment cannot be checked in")
    tz = _facility_tz(session, appt.facility_id)
    if appt.start_at.astimezone(tz).date() != _now().astimezone(tz).date():
        raise Conflict("Only today's appointments can be checked in")
    appt.checked_in_at = _now()
    appt.status = "WAITING"
    entry = _issue_token(session, appt, priority)
    _event(session, principal, "PATIENT_CHECKED_IN", appt, {"token": entry.token_number})
    session.commit()
    return _appointment_out(session, appt.id)


def walk_in(session: Session, principal: Principal, body: WalkInCreate) -> AppointmentOut:
    org_id = _org(principal)
    patient = session.get(Patient, body.patient_id)
    if patient is None or patient.status != "ACTIVE":
        raise NotFound("Patient not found")
    facility_id, minutes = body.facility_id, 15
    if body.practitioner_id:
        p = _get_practitioner(session, body.practitioner_id)
        facility_id, minutes = p.facility_id, p.consultation_minutes
        if body.facility_id != p.facility_id:
            raise AppError("The doctor works at a different facility")
    elif session.get(Facility, facility_id) is None:
        raise NotFound("Facility not found")
    now = _now()
    existing = session.scalar(
        select(Appointment.id).where(
            Appointment.patient_id == patient.id,
            Appointment.status.in_(("WAITING", "CHECKED_IN", "IN_CONSULTATION")),
        )
    )
    if existing:
        raise Conflict("The patient is already checked in")
    appt = Appointment(
        organisation_id=org_id,
        patient_id=patient.id,
        practitioner_id=body.practitioner_id,
        facility_id=facility_id,
        kind="WALK_IN",
        status="WAITING",
        start_at=now,
        end_at=now + timedelta(minutes=minutes),
        reason=body.reason,
        booked_by=principal.user_id,
        checked_in_at=now,
    )
    session.add(appt)
    session.flush()
    entry = _issue_token(session, appt, body.priority)
    _event(
        session,
        principal,
        "PATIENT_CHECKED_IN",
        appt,
        {"token": entry.token_number, "walk_in": True},
    )
    session.commit()
    return _appointment_out(session, appt.id)


def queue(
    session: Session,
    facility_id: uuid.UUID,
    practitioner_id: uuid.UUID | None,
    include_active: bool,
) -> list[QueueItem]:
    tz = _facility_tz(session, facility_id)
    today = _now().astimezone(tz).date()
    statuses = ["WAITING", "CHECKED_IN"] + (["IN_CONSULTATION"] if include_active else [])
    stmt = (
        select(QueueEntry, Appointment.status, Patient, User.full_name)
        .join(Appointment, Appointment.id == QueueEntry.appointment_id)
        .join(Patient, Patient.id == QueueEntry.patient_id)
        .outerjoin(Practitioner, Practitioner.id == QueueEntry.practitioner_id)
        .outerjoin(User, User.id == Practitioner.user_id)
        .where(
            QueueEntry.facility_id == facility_id,
            QueueEntry.token_date == today,
            Appointment.status.in_(statuses),
        )
    )
    if practitioner_id:
        stmt = stmt.where(
            (QueueEntry.practitioner_id == practitioner_id) | QueueEntry.practitioner_id.is_(None)
        )
    # Urgent first, then arrival order (token numbers are issued in arrival order).
    rows = session.execute(
        stmt.order_by((QueueEntry.priority != "URGENT"), QueueEntry.token_number)
    ).all()
    return [
        QueueItem(
            appointment_id=q.appointment_id,
            token_number=q.token_number,
            priority=q.priority,
            status=status,
            patient_id=pt.id,
            patient_name=pt.full_name,
            patient_mrn=pt.mrn,
            age_years=age_years(pt.date_of_birth, today),
            administrative_gender=pt.administrative_gender,
            practitioner_id=q.practitioner_id,
            practitioner_name=dname,
            waiting_since=q.created_at,
        )
        for q, status, pt, dname in rows
    ]
