import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.modules.audit.service import emit_event, record_audit
from app.modules.clinical import reference_ranges as rr
from app.modules.clinical.encounters import get_encounter, open_encounter, require_owner
from app.modules.clinical.models import (
    FollowUp,
    InvestigationResult,
    Prescription,
    PrescriptionItem,
    ServiceRequest,
)
from app.modules.clinical.safety import check_prescription
from app.modules.clinical.schemas import (
    FollowUpIn,
    FollowUpOut,
    PrescriptionIn,
    PrescriptionItemOut,
    PrescriptionOut,
    ResultIn,
    ResultOut,
    SafetyCheckOut,
    ServiceRequestIn,
    ServiceRequestOut,
)
from app.modules.cover.service import covering_for
from app.modules.patients.models import Patient


class WarningsNeedAcknowledgement(AppError):
    status_code = 409
    code = "warnings_require_acknowledgement"


def _org(principal: Principal) -> uuid.UUID:
    assert principal.org_id is not None
    return principal.org_id


def _log(
    session: Session,
    principal: Principal,
    event: str,
    kind: str,
    row_id: uuid.UUID,
    patient_id: uuid.UUID,
    encounter_id: uuid.UUID | None,
    payload: dict[str, object] | None = None,
) -> None:
    org_id = _org(principal)
    emit_event(
        session,
        org_id=org_id,
        event_type=event,
        aggregate_type=kind,
        aggregate_id=row_id,
        patient_id=patient_id,
        encounter_id=encounter_id,
        actor_user_id=principal.user_id,
        payload=payload,
    )
    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action=event,
        resource_type=kind,
        resource_id=row_id,
        after=payload,
    )


# ---- prescriptions -----------------------------------------------------------------


def _items(session: Session, rx_id: uuid.UUID) -> list[PrescriptionItem]:
    return list(
        session.scalars(
            select(PrescriptionItem)
            .where(PrescriptionItem.prescription_id == rx_id)
            .order_by(PrescriptionItem.position)
        )
    )


def prescription_out(session: Session, rx: Prescription) -> PrescriptionOut:
    out = PrescriptionOut.model_validate(rx)
    out.items = [PrescriptionItemOut.model_validate(i) for i in _items(session, rx.id)]
    return out


def _get_rx(session: Session, rx_id: uuid.UUID, *, lock: bool = False) -> Prescription:
    stmt = select(Prescription).where(Prescription.id == rx_id)
    rx = session.scalar(stmt.with_for_update() if lock else stmt)
    if rx is None:
        raise NotFound("Prescription not found")
    return rx


def _write_items(
    session: Session, principal: Principal, rx: Prescription, body: PrescriptionIn
) -> None:
    for pos, item in enumerate(body.items, start=1):
        session.add(
            PrescriptionItem(
                organisation_id=_org(principal),
                prescription_id=rx.id,
                position=pos,
                **item.model_dump(),
            )
        )


def create_prescription(
    session: Session, principal: Principal, encounter_id: uuid.UUID, body: PrescriptionIn
) -> PrescriptionOut:
    enc = open_encounter(session, encounter_id)
    me = require_owner(session, principal, enc)
    if enc.status != "IN_PROGRESS":
        raise Conflict("Start the consultation before prescribing")
    rx = Prescription(
        organisation_id=_org(principal),
        patient_id=enc.patient_id,
        encounter_id=enc.id,
        practitioner_id=me.id,
        notes=body.notes,
        created_by=principal.user_id,
    )
    session.add(rx)
    session.flush()
    _write_items(session, principal, rx, body)
    session.flush()
    _log(session, principal, "PRESCRIPTION_DRAFTED", "prescriptions", rx.id, rx.patient_id, enc.id)
    session.commit()
    return prescription_out(session, rx)


def update_prescription(
    session: Session, principal: Principal, rx_id: uuid.UUID, body: PrescriptionIn
) -> PrescriptionOut:
    rx = _get_rx(session, rx_id, lock=True)
    enc = open_encounter(session, rx.encounter_id)
    require_owner(session, principal, enc)
    if rx.status != "DRAFT":
        raise Conflict("A signed prescription cannot be edited. Void it and write a new one.")
    for old in _items(session, rx.id):
        session.delete(old)
    session.flush()
    rx.notes = body.notes
    _write_items(session, principal, rx, body)
    session.flush()
    record_audit(
        session,
        principal.meta,
        org_id=_org(principal),
        actor_user_id=principal.user_id,
        action="PRESCRIPTION_EDITED",
        resource_type="prescriptions",
        resource_id=rx.id,
    )
    session.commit()
    return prescription_out(session, rx)


def safety_check(session: Session, principal: Principal, rx_id: uuid.UUID) -> SafetyCheckOut:
    rx = _get_rx(session, rx_id)
    return check_prescription(session, rx.patient_id, _items(session, rx.id))


def sign_prescription(
    session: Session, principal: Principal, rx_id: uuid.UUID, acknowledged: list[str]
) -> PrescriptionOut:
    rx = _get_rx(session, rx_id, lock=True)
    enc = open_encounter(session, rx.encounter_id)
    require_owner(session, principal, enc)
    if rx.status != "DRAFT":
        raise Conflict("Only a draft can be signed")
    items = _items(session, rx.id)
    result = check_prescription(session, rx.patient_id, items)
    outstanding = [
        w for w in result.warnings if w.level == "WARNING" and w.code not in set(acknowledged)
    ]
    if outstanding:
        raise WarningsNeedAcknowledgement(
            "Review the safety warnings and acknowledge each one to sign.",
            extra={"warnings": [w.model_dump() for w in outstanding]},
        )
    rx.status = "SIGNED"
    rx.signed_at = datetime.now(UTC)
    rx.signed_by = principal.user_id
    rx.safety_snapshot = {
        "warnings": [w.model_dump() for w in result.warnings],
        "acknowledged": sorted(set(acknowledged)),
        "checks_not_performed": result.checks_not_performed,
    }
    session.flush()
    _log(
        session,
        principal,
        "PRESCRIPTION_SIGNED",
        "prescriptions",
        rx.id,
        rx.patient_id,
        enc.id,
        {"items": len(items), "acknowledged_warnings": len(acknowledged)},
    )
    session.commit()
    return prescription_out(session, rx)


def void_prescription(
    session: Session, principal: Principal, rx_id: uuid.UUID, reason: str
) -> PrescriptionOut:
    rx = _get_rx(session, rx_id, lock=True)
    enc = get_encounter(session, rx.encounter_id)
    require_owner(session, principal, enc)
    if rx.status == "VOIDED":
        raise Conflict("Already voided")
    if rx.status == "SIGNED" and not principal.has("prescription:sign"):
        raise Forbidden("Only a doctor can void a signed prescription")
    rx.status = "VOIDED"
    rx.void_reason = reason
    rx.voided_at = datetime.now(UTC)
    rx.voided_by = principal.user_id
    _log(session, principal, "PRESCRIPTION_VOIDED", "prescriptions", rx.id, rx.patient_id, enc.id)
    session.commit()
    return prescription_out(session, rx)


def get_prescription(session: Session, principal: Principal, rx_id: uuid.UUID) -> PrescriptionOut:
    rx = _get_rx(session, rx_id)
    if rx.status == "DRAFT" and not principal.has("prescription:write"):
        raise NotFound("Prescription not found")  # drafts are invisible to non-authors
    record_audit(
        session,
        principal.meta,
        org_id=_org(principal),
        actor_user_id=principal.user_id,
        action="PRESCRIPTION_VIEWED",
        resource_type="prescriptions",
        resource_id=rx.id,
    )
    session.commit()
    return prescription_out(session, rx)


def patient_prescriptions(
    session: Session, principal: Principal, patient_id: uuid.UUID
) -> list[PrescriptionOut]:
    stmt = select(Prescription).where(Prescription.patient_id == patient_id)
    if not principal.has("prescription:write"):
        stmt = stmt.where(Prescription.status == "SIGNED")
    rows = session.scalars(stmt.order_by(Prescription.created_at.desc()).limit(50)).all()
    return [prescription_out(session, r) for r in rows]


# ---- investigations ----------------------------------------------------------------

_TECH_CATEGORY = {"lab_technician": "LAB", "radiology_technician": "RADIOLOGY"}


def _tech_scope(principal: Principal) -> str | None:
    """Technicians see only their own department's requests."""
    if principal.has("encounter:read"):
        return None
    for role, category in _TECH_CATEGORY.items():
        if role in principal.roles:
            return category
    return None


def _order_out(session: Session, sr: ServiceRequest) -> ServiceRequestOut:
    out = ServiceRequestOut.model_validate(sr)
    patient = session.get(Patient, sr.patient_id)
    if patient:
        out.patient_name, out.patient_mrn = patient.full_name, patient.mrn
    return out


def create_order(
    session: Session, principal: Principal, encounter_id: uuid.UUID, body: ServiceRequestIn
) -> ServiceRequestOut:
    enc = open_encounter(session, encounter_id)
    require_owner(session, principal, enc)
    sr = ServiceRequest(
        organisation_id=_org(principal),
        patient_id=enc.patient_id,
        encounter_id=enc.id,
        category=body.category,
        name=body.name.strip(),
        code=body.code,
        code_system=body.code_system,
        priority=body.priority,
        reason=body.reason,
        created_by=principal.user_id,
    )
    session.add(sr)
    session.flush()
    _log(
        session,
        principal,
        "INVESTIGATION_DRAFTED",
        "service_requests",
        sr.id,
        sr.patient_id,
        enc.id,
    )
    session.commit()
    return _order_out(session, sr)


def _get_order(session: Session, order_id: uuid.UUID, *, lock: bool = False) -> ServiceRequest:
    stmt = select(ServiceRequest).where(ServiceRequest.id == order_id)
    sr = session.scalar(stmt.with_for_update() if lock else stmt)
    if sr is None:
        raise NotFound("Order not found")
    return sr


def place_order(session: Session, principal: Principal, order_id: uuid.UUID) -> ServiceRequestOut:
    sr = _get_order(session, order_id, lock=True)
    enc = open_encounter(session, sr.encounter_id)
    require_owner(session, principal, enc)
    if sr.status != "DRAFT":
        raise Conflict("Only a draft order can be placed")
    sr.status = "ORDERED"
    sr.ordered_by = principal.user_id
    sr.ordered_at = datetime.now(UTC)
    _log(
        session,
        principal,
        "INVESTIGATION_ORDERED",
        "service_requests",
        sr.id,
        sr.patient_id,
        enc.id,
        {"category": sr.category, "priority": sr.priority},
    )
    session.commit()
    return _order_out(session, sr)


def cancel_order(
    session: Session, principal: Principal, order_id: uuid.UUID, reason: str
) -> ServiceRequestOut:
    sr = _get_order(session, order_id, lock=True)
    enc = get_encounter(session, sr.encounter_id)
    require_owner(session, principal, enc)
    if sr.status not in ("DRAFT", "ORDERED"):
        raise Conflict("This order can no longer be cancelled")
    sr.status = "CANCELLED"
    sr.cancel_reason = reason
    _log(
        session,
        principal,
        "INVESTIGATION_CANCELLED",
        "service_requests",
        sr.id,
        sr.patient_id,
        enc.id,
    )
    session.commit()
    return _order_out(session, sr)


def list_orders(
    session: Session,
    principal: Principal,
    *,
    encounter_id: uuid.UUID | None,
    patient_id: uuid.UUID | None,
    category: str | None,
    status: str | None,
) -> list[ServiceRequestOut]:
    stmt = select(ServiceRequest)
    scope = _tech_scope(principal)
    if scope:
        category = scope
    if scope or not principal.has("order:write"):
        # A draft is a decision not yet made: only the people who can place orders see it.
        stmt = stmt.where(ServiceRequest.status != "DRAFT")
    if encounter_id:
        stmt = stmt.where(ServiceRequest.encounter_id == encounter_id)
    if patient_id:
        stmt = stmt.where(ServiceRequest.patient_id == patient_id)
    if category:
        stmt = stmt.where(ServiceRequest.category == category)
    if status:
        stmt = stmt.where(ServiceRequest.status == status)
    rows = session.scalars(stmt.order_by(ServiceRequest.created_at.desc()).limit(100)).all()
    return [_order_out(session, r) for r in rows]


def enter_result(
    session: Session, principal: Principal, order_id: uuid.UUID, body: ResultIn
) -> ResultOut:
    sr = _get_order(session, order_id, lock=True)
    scope = _tech_scope(principal)
    if scope and sr.category != scope:
        raise NotFound("Order not found")
    if sr.status not in ("ORDERED", "RESULTED"):
        raise Conflict("Results can only be entered for placed orders")
    res = InvestigationResult(
        organisation_id=_org(principal),
        patient_id=sr.patient_id,
        service_request_id=sr.id,
        test_name=body.test_name.strip(),
        value_numeric=body.value_numeric,
        value_text=body.value_text,
        unit=body.unit,
        ref_low=body.ref_low,
        ref_high=body.ref_high,
        critical_low=body.critical_low,
        critical_high=body.critical_high,
        comment=body.comment,
        interpretation=rr.interpret_lab(
            body.value_numeric, body.ref_low, body.ref_high, body.critical_low, body.critical_high
        ),
        reported_by=principal.user_id,
    )
    session.add(res)
    sr.status = "RESULTED"
    session.flush()
    _log(
        session,
        principal,
        "RESULT_RECEIVED",
        "investigation_results",
        res.id,
        res.patient_id,
        sr.encounter_id,
        {"interpretation": res.interpretation},
    )
    session.commit()
    return ResultOut.model_validate(res)


def review_result(session: Session, principal: Principal, result_id: uuid.UUID) -> ResultOut:
    res = session.get(InvestigationResult, result_id)
    if res is None:
        raise NotFound("Result not found")
    if res.reviewed_at is None:
        res.reviewed_at = datetime.now(UTC)
        res.reviewed_by = principal.user_id
        ordered_by = session.scalar(
            select(ServiceRequest.ordered_by).where(ServiceRequest.id == res.service_request_id)
        )
        on_behalf = ordered_by is not None and ordered_by != principal.user_id
        _log(
            session,
            principal,
            "RESULT_REVIEWED",
            "investigation_results",
            res.id,
            res.patient_id,
            None,
            {"on_behalf_of": str(ordered_by)} if on_behalf else None,
        )
    session.commit()
    return ResultOut.model_validate(res)


def results_awaiting_review(session: Session, principal: Principal) -> list[ResultOut]:
    """Abnormal-first list of unreviewed results for orders this doctor placed, plus those of any
    colleague who has currently asked this doctor to cover."""
    covered = covering_for(session, principal.user_id)
    rows = session.execute(
        select(InvestigationResult, ServiceRequest.ordered_by)
        .join(ServiceRequest, ServiceRequest.id == InvestigationResult.service_request_id)
        .where(
            InvestigationResult.reviewed_at.is_(None),
            ServiceRequest.ordered_by.in_([principal.user_id, *covered]),
        )
        .order_by(InvestigationResult.reported_at.desc())
        .limit(100)
    ).all()
    rank = {"CRITICAL_LOW": 0, "CRITICAL_HIGH": 0, "LOW": 1, "HIGH": 1}
    out = []
    for res, ordered_by in rows:
        item = ResultOut.model_validate(res)
        if ordered_by is not None and ordered_by != principal.user_id:
            item.covering_for = covered.get(ordered_by)
        out.append(item)
    return sorted(out, key=lambda r: rank.get(r.interpretation, 2))


def patient_results(session: Session, patient_id: uuid.UUID) -> list[ResultOut]:
    rows = session.scalars(
        select(InvestigationResult)
        .where(InvestigationResult.patient_id == patient_id)
        .order_by(InvestigationResult.reported_at.desc())
        .limit(100)
    ).all()
    return [ResultOut.model_validate(r) for r in rows]


# ---- follow-ups --------------------------------------------------------------------


def create_followup(
    session: Session, principal: Principal, encounter_id: uuid.UUID, body: FollowUpIn
) -> FollowUpOut:
    enc = open_encounter(session, encounter_id)
    require_owner(session, principal, enc)
    fu = FollowUp(
        organisation_id=_org(principal),
        patient_id=enc.patient_id,
        encounter_id=enc.id,
        due_date=body.due_date,
        kind=body.kind,
        reason=body.reason,
        created_by=principal.user_id,
    )
    session.add(fu)
    session.flush()
    _log(
        session,
        principal,
        "FOLLOWUP_CREATED",
        "follow_ups",
        fu.id,
        fu.patient_id,
        enc.id,
        {"kind": fu.kind, "due": fu.due_date.isoformat()},
    )
    session.commit()
    return FollowUpOut.model_validate(fu)


def list_followups(
    session: Session,
    *,
    patient_id: uuid.UUID | None,
    due_on_or_before: date | None,
    status: str | None,
) -> list[FollowUpOut]:
    stmt = select(FollowUp)
    if patient_id:
        stmt = stmt.where(FollowUp.patient_id == patient_id)
    if due_on_or_before:
        stmt = stmt.where(FollowUp.due_date <= due_on_or_before)
    if status:
        stmt = stmt.where(FollowUp.status == status)
    return [
        FollowUpOut.model_validate(f)
        for f in session.scalars(stmt.order_by(FollowUp.due_date).limit(200))
    ]


def set_followup_status(
    session: Session, principal: Principal, followup_id: uuid.UUID, status: str
) -> FollowUpOut:
    fu = session.get(FollowUp, followup_id)
    if fu is None:
        raise NotFound("Follow-up not found")
    if fu.status != "PENDING":
        raise Conflict("This follow-up is already closed")
    fu.status = status
    fu.completed_at = datetime.now(UTC)
    _log(
        session,
        principal,
        f"FOLLOWUP_{status}",
        "follow_ups",
        fu.id,
        fu.patient_id,
        fu.encounter_id,
    )
    session.commit()
    return FollowUpOut.model_validate(fu)
