import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import Conflict, Forbidden, NotFound
from app.modules.audit.service import emit_event, record_audit
from app.modules.clinical.facts import current_filter
from app.modules.clinical.models import (
    ClinicalNote,
    Condition,
    Encounter,
    FollowUp,
    Observation,
    Prescription,
    ServiceRequest,
)
from app.modules.clinical.schemas import (
    ConditionOut,
    EncounterDetail,
    EncounterOut,
    FollowUpOut,
    NoteOut,
    ObservationOut,
    ServiceRequestOut,
)
from app.modules.scheduling import service as scheduling
from app.modules.scheduling.models import Appointment, Practitioner, QueueEntry

OPEN = ("TRIAGE", "IN_PROGRESS")


def _org(principal: Principal) -> uuid.UUID:
    assert principal.org_id is not None
    return principal.org_id


def get_encounter(session: Session, encounter_id: uuid.UUID, *, lock: bool = False) -> Encounter:
    stmt = select(Encounter).where(Encounter.id == encounter_id)
    enc = session.scalar(stmt.with_for_update() if lock else stmt)
    if enc is None:
        raise NotFound("Encounter not found")
    return enc


def open_encounter(session: Session, encounter_id: uuid.UUID) -> Encounter:
    """Clinical writes are only accepted while the visit is open."""
    enc = get_encounter(session, encounter_id)
    if enc.status not in OPEN:
        raise Conflict("This visit is closed; it can no longer be changed")
    return enc


def practitioner_for(session: Session, principal: Principal) -> Practitioner | None:
    return session.scalar(select(Practitioner).where(Practitioner.user_id == principal.user_id))


def require_owner(session: Session, principal: Principal, enc: Encounter) -> Practitioner:
    """Only the responsible doctor writes clinical content to an encounter."""
    mine = practitioner_for(session, principal)
    if mine is None or enc.practitioner_id != mine.id:
        raise Forbidden("This consultation belongs to another doctor")
    return mine


def start_triage(
    session: Session, principal: Principal, appointment_id: uuid.UUID
) -> tuple[Encounter, bool]:
    org_id = _org(principal)
    existing = session.scalar(select(Encounter).where(Encounter.appointment_id == appointment_id))
    if existing:
        return existing, False
    appt = session.scalar(
        select(Appointment).where(Appointment.id == appointment_id).with_for_update()
    )
    if appt is None:
        raise NotFound("Appointment not found")
    if appt.status not in ("WAITING", "CHECKED_IN"):
        raise Conflict("The patient must be checked in before triage")
    enc = Encounter(
        organisation_id=org_id,
        patient_id=appt.patient_id,
        facility_id=appt.facility_id,
        practitioner_id=appt.practitioner_id,
        appointment_id=appt.id,
        status="TRIAGE",
        started_at=datetime.now(UTC),
        created_by=principal.user_id,
    )
    session.add(enc)
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError:  # two staff opened triage for the same visit at once
        session.rollback()
        return session.scalars(
            select(Encounter).where(Encounter.appointment_id == appointment_id)
        ).one(), False
    _log(session, principal, "TRIAGE_STARTED", enc)
    session.commit()
    return enc, True


def start_consultation(
    session: Session, principal: Principal, appointment_id: uuid.UUID
) -> Encounter:
    org_id = _org(principal)
    me = practitioner_for(session, principal)
    if me is None:
        raise Conflict(
            "Your account has no practitioner profile; ask an administrator to set one up"
        )
    enc = session.scalar(
        select(Encounter).where(Encounter.appointment_id == appointment_id).with_for_update()
    )
    if enc is not None:
        if enc.status == "COMPLETED":
            raise Conflict("This visit is already completed")
        if enc.status == "IN_PROGRESS":
            require_owner(session, principal, enc)
            return enc  # idempotent: the doctor tapped twice or reopened the app
    appt = session.scalar(select(Appointment).where(Appointment.id == appointment_id))
    if appt is None:
        raise NotFound("Appointment not found")
    if appt.practitioner_id not in (None, me.id):
        raise Forbidden("This patient is booked with another doctor")
    scheduling.transition(
        session, principal, appointment_id, "IN_CONSULTATION", assign_practitioner_id=me.id
    )
    now = datetime.now(UTC)
    if enc is None:
        enc = Encounter(
            organisation_id=org_id,
            patient_id=appt.patient_id,
            facility_id=appt.facility_id,
            appointment_id=appt.id,
            status="IN_PROGRESS",
            started_at=now,
            created_by=principal.user_id,
        )
        session.add(enc)
    enc.practitioner_id = me.id
    enc.status = "IN_PROGRESS"
    enc.consultation_started_at = now
    session.flush()
    _log(session, principal, "ENCOUNTER_STARTED", enc)
    session.commit()
    return enc


def set_triage_category(
    session: Session, principal: Principal, encounter_id: uuid.UUID, category: str
) -> Encounter:
    enc = open_encounter(session, encounter_id)
    before = enc.triage_category
    enc.triage_category = category
    record_audit(
        session,
        principal.meta,
        org_id=_org(principal),
        actor_user_id=principal.user_id,
        action="TRIAGE_CATEGORY_SET",
        resource_type="encounter",
        resource_id=enc.id,
        before={"category": before},
        after={"category": category},
    )
    session.commit()
    return enc


def complete(session: Session, principal: Principal, encounter_id: uuid.UUID) -> Encounter:
    enc = get_encounter(session, encounter_id, lock=True)
    require_owner(session, principal, enc)
    if enc.status != "IN_PROGRESS":
        raise Conflict("Only a consultation in progress can be completed")
    # Nothing may be left half-decided: a draft is an unmade clinical decision.
    drafts = (
        session.scalar(
            select(func.count())
            .select_from(Prescription)
            .where(Prescription.encounter_id == enc.id, Prescription.status == "DRAFT")
        )
        or 0
    )
    draft_orders = (
        session.scalar(
            select(func.count())
            .select_from(ServiceRequest)
            .where(ServiceRequest.encounter_id == enc.id, ServiceRequest.status == "DRAFT")
        )
        or 0
    )
    if drafts or draft_orders:
        raise Conflict(
            f"Resolve drafts first: {drafts} prescription(s) and {draft_orders} order(s) are "
            "not signed or placed. Sign, place or discard them."
        )
    enc.status = "COMPLETED"
    enc.ended_at = datetime.now(UTC)
    scheduling.transition(session, principal, enc.appointment_id, "COMPLETED")
    _log(session, principal, "ENCOUNTER_COMPLETED", enc)
    session.commit()
    return enc


def handover(
    session: Session, principal: Principal, encounter_id: uuid.UUID, to_practitioner_id: uuid.UUID
) -> Encounter:
    """The responsible doctor passes an open consultation to a colleague at the same facility.

    Nothing the first doctor wrote changes hands silently: unsigned prescriptions and unplaced
    orders must be finished first, and a recording they started must be stopped, so the new
    doctor never signs or inherits someone else's half-finished work."""
    from app.modules.interactions.models import ClinicalInteraction

    enc = get_encounter(session, encounter_id, lock=True)
    if enc.status != "IN_PROGRESS":
        raise Conflict("Only a consultation that is under way can be handed over")
    require_owner(session, principal, enc)
    target = session.get(Practitioner, to_practitioner_id)
    if target is None or target.status != "ACTIVE" or target.id == enc.practitioner_id:
        raise NotFound("That doctor was not found")
    if target.facility_id != enc.facility_id:
        raise Conflict("The other doctor works at a different site")
    drafts = session.scalar(
        select(func.count())
        .select_from(Prescription)
        .where(Prescription.encounter_id == enc.id, Prescription.status == "DRAFT")
    )
    draft_orders = session.scalar(
        select(func.count())
        .select_from(ServiceRequest)
        .where(ServiceRequest.encounter_id == enc.id, ServiceRequest.status == "DRAFT")
    )
    if drafts or draft_orders:
        raise Conflict(
            f"Resolve drafts first: {drafts or 0} prescription(s) and {draft_orders or 0} order(s) "
            "are not signed or placed. Sign, place or discard them."
        )
    recording = session.scalar(
        select(func.count())
        .select_from(ClinicalInteraction)
        .where(
            ClinicalInteraction.encounter_id == enc.id,
            ClinicalInteraction.status.in_(("CREATED", "ACTIVE", "PAUSED")),
        )
    )
    if recording:
        raise Conflict("Stop the recording before handing over")

    previous = enc.practitioner_id
    enc.practitioner_id = target.id
    appointment = session.get(Appointment, enc.appointment_id)
    if appointment is not None:
        appointment.practitioner_id = target.id
    queue = session.scalar(
        select(QueueEntry).where(QueueEntry.appointment_id == enc.appointment_id)
    )
    if queue is not None:
        queue.practitioner_id = target.id
    emit_event(
        session,
        org_id=_org(principal),
        event_type="ENCOUNTER_HANDED_OVER",
        aggregate_type="encounter",
        aggregate_id=enc.id,
        patient_id=enc.patient_id,
        encounter_id=enc.id,
        actor_user_id=principal.user_id,
        payload={"from_practitioner_id": str(previous), "to_practitioner_id": str(target.id)},
    )
    record_audit(
        session,
        principal.meta,
        org_id=_org(principal),
        actor_user_id=principal.user_id,
        action="ENCOUNTER_HANDED_OVER",
        resource_type="encounter",
        resource_id=enc.id,
        before={"practitioner_id": str(previous)},
        after={"practitioner_id": str(target.id)},
    )
    session.commit()
    return enc


def _log(session: Session, principal: Principal, event_type: str, enc: Encounter) -> None:
    org_id = _org(principal)
    emit_event(
        session,
        org_id=org_id,
        event_type=event_type,
        aggregate_type="encounter",
        aggregate_id=enc.id,
        patient_id=enc.patient_id,
        encounter_id=enc.id,
        actor_user_id=principal.user_id,
    )
    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action=event_type,
        resource_type="encounter",
        resource_id=enc.id,
    )


def detail(session: Session, principal: Principal, encounter_id: uuid.UUID) -> EncounterDetail:
    from app.modules.clinical.orders import prescription_out

    enc = get_encounter(session, encounter_id)
    notes = session.scalars(
        select(ClinicalNote)
        .where(ClinicalNote.encounter_id == enc.id, ClinicalNote.is_current)
        .order_by(ClinicalNote.recorded_at)
    ).all()
    vitals = session.scalars(
        select(Observation)
        .where(Observation.encounter_id == enc.id, Observation.is_current)
        .order_by(Observation.observed_at)
    ).all()
    conditions = session.scalars(
        select(Condition).where(Condition.encounter_id == enc.id, *current_filter(Condition))
    ).all()
    rxs = session.scalars(
        select(Prescription)
        .where(Prescription.encounter_id == enc.id)
        .order_by(Prescription.created_at)
    ).all()
    if "prescription:write" not in principal.permissions:
        rxs = [r for r in rxs if r.status == "SIGNED"]
    orders = session.scalars(
        select(ServiceRequest)
        .where(ServiceRequest.encounter_id == enc.id)
        .order_by(ServiceRequest.created_at)
    ).all()
    if "order:write" not in principal.permissions:
        orders = [o for o in orders if o.status != "DRAFT"]
    fups = session.scalars(select(FollowUp).where(FollowUp.encounter_id == enc.id)).all()
    record_audit(
        session,
        principal.meta,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        action="ENCOUNTER_VIEWED",
        resource_type="encounter",
        resource_id=enc.id,
    )
    session.commit()
    return EncounterDetail(
        encounter=EncounterOut.model_validate(enc),
        notes=[NoteOut.model_validate(n) for n in notes],
        vitals=[ObservationOut.model_validate(v) for v in vitals],
        conditions=[ConditionOut.model_validate(c) for c in conditions],
        prescriptions=[prescription_out(session, r) for r in rxs],
        orders=[ServiceRequestOut.model_validate(o) for o in orders],
        follow_ups=[FollowUpOut.model_validate(f) for f in fups],
    )


def list_for_patient(
    session: Session, principal: Principal, patient_id: uuid.UUID
) -> list[Encounter]:
    return list(
        session.scalars(
            select(Encounter)
            .where(Encounter.patient_id == patient_id)
            .order_by(Encounter.started_at.desc())
            .limit(50)
        )
    )
