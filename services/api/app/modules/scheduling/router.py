import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.context import Principal
from app.core.deps import TenantDb, require
from app.modules.scheduling import service
from app.modules.scheduling.schemas import (
    AppointmentCreate,
    AppointmentOut,
    CancelRequest,
    CheckInRequest,
    PractitionerCreate,
    PractitionerOut,
    QueueItem,
    RescheduleRequest,
    SlotOut,
    WalkInCreate,
    WorkingHoursUpdate,
)

router = APIRouter(tags=["scheduling"])

Manage = Annotated[Principal, Depends(require("appointment:manage"))]
ReadAppt = Annotated[Principal, Depends(require("appointment:read"))]
QueueManage = Annotated[Principal, Depends(require("queue:manage"))]


@router.post("/practitioners", response_model=PractitionerOut, status_code=201)
def create_practitioner(
    body: PractitionerCreate,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("practitioner:manage"))],
) -> PractitionerOut:
    return service.create_practitioner(db, principal, body)


@router.get("/practitioners", response_model=list[PractitionerOut])
def list_practitioners(
    db: TenantDb,
    _: Annotated[Principal, Depends(require("practitioner:read"))],
    facility_id: uuid.UUID | None = None,
    specialty: Annotated[str | None, Query(max_length=100)] = None,
) -> list[PractitionerOut]:
    return service.list_practitioners(db, facility_id, specialty)


@router.put("/practitioners/{practitioner_id}/working-hours", response_model=PractitionerOut)
def set_working_hours(
    practitioner_id: uuid.UUID,
    body: WorkingHoursUpdate,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("practitioner:manage"))],
) -> PractitionerOut:
    return service.set_working_hours(db, principal, practitioner_id, body.hours)


@router.get("/practitioners/{practitioner_id}/slots", response_model=list[SlotOut])
def slots(
    practitioner_id: uuid.UUID,
    on: date,
    db: TenantDb,
    _: Annotated[Principal, Depends(require("appointment:read"))],
) -> list[SlotOut]:
    return service.available_slots(db, practitioner_id, on)


@router.post("/appointments", response_model=AppointmentOut, status_code=201)
def book(body: AppointmentCreate, db: TenantDb, principal: Manage) -> AppointmentOut:
    return service.book(db, principal, body)


@router.get("/appointments", response_model=list[AppointmentOut])
def list_appointments(
    db: TenantDb,
    _: ReadAppt,
    on: date | None = None,
    practitioner_id: uuid.UUID | None = None,
    facility_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    status: Annotated[str | None, Query(max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AppointmentOut]:
    return service.list_appointments(
        db,
        day=on,
        practitioner_id=practitioner_id,
        facility_id=facility_id,
        patient_id=patient_id,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.post("/appointments/{appointment_id}/reschedule", response_model=AppointmentOut)
def reschedule(
    appointment_id: uuid.UUID, body: RescheduleRequest, db: TenantDb, principal: Manage
) -> AppointmentOut:
    return service.reschedule(db, principal, appointment_id, body.start_at)


@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel(
    appointment_id: uuid.UUID, body: CancelRequest, db: TenantDb, principal: Manage
) -> AppointmentOut:
    return service.cancel(db, principal, appointment_id, body.reason)


@router.post("/appointments/{appointment_id}/confirm", response_model=AppointmentOut)
def confirm(appointment_id: uuid.UUID, db: TenantDb, principal: Manage) -> AppointmentOut:
    return service.set_simple_status(db, principal, appointment_id, "CONFIRMED")


@router.post("/appointments/{appointment_id}/no-show", response_model=AppointmentOut)
def no_show(appointment_id: uuid.UUID, db: TenantDb, principal: Manage) -> AppointmentOut:
    return service.set_simple_status(db, principal, appointment_id, "NO_SHOW")


@router.post("/appointments/{appointment_id}/check-in", response_model=AppointmentOut)
def check_in(
    appointment_id: uuid.UUID, body: CheckInRequest, db: TenantDb, principal: QueueManage
) -> AppointmentOut:
    return service.check_in(db, principal, appointment_id, body.priority)


@router.post("/walk-ins", response_model=AppointmentOut, status_code=201)
def walk_in(body: WalkInCreate, db: TenantDb, principal: QueueManage) -> AppointmentOut:
    return service.walk_in(db, principal, body)


@router.get("/queue", response_model=list[QueueItem])
def queue(
    facility_id: uuid.UUID,
    db: TenantDb,
    _: Annotated[Principal, Depends(require("queue:read"))],
    practitioner_id: uuid.UUID | None = None,
    include_active: bool = True,
) -> list[QueueItem]:
    return service.queue(db, facility_id, practitioner_id, include_active)
