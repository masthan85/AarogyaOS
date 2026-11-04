"""Procedures, immunisations and referrals.

Same rules as every other clinical fact: provenance on each row, a doctor's entry counts as
confirmed, anyone else's waits for a clinician, and a correction adds a new version.
"""

import uuid
from datetime import date, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.deps import TenantDb, require
from app.core.errors import AppError
from app.modules.audit.service import emit_event, record_audit
from app.modules.clinical.encounters import open_encounter
from app.modules.clinical.facts import current_filter, get_fact, provenance_for_new, supersede
from app.modules.clinical.models import Immunisation, ProcedureRecord, Referral
from app.modules.clinical.schemas import ClientSource, FactOut

router = APIRouter(tags=["clinical-history"])


class _Coded(BaseModel):
    code: str | None = Field(default=None, max_length=40)
    code_system: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def _both_or_neither(self) -> "_Coded":
        if (self.code is None) != (self.code_system is None):
            raise ValueError("Provide a code together with its code system")
        return self


def _not_future(value: date | None, what: str) -> None:
    if value is not None and value > date.today() + timedelta(days=1):
        raise ValueError(f"{what} cannot be in the future")


class ProcedureIn(_Coded):
    display: str = Field(min_length=2, max_length=300)
    performed_on: date
    status: Literal["COMPLETED", "ABANDONED"] = "COMPLETED"
    body_site: str | None = Field(default=None, max_length=120)
    outcome: str | None = Field(default=None, max_length=500)
    complications: str | None = Field(default=None, max_length=500)
    source: ClientSource | None = None

    @model_validator(mode="after")
    def _date(self) -> "ProcedureIn":
        _not_future(self.performed_on, "The date performed")
        return self


class ProcedureEdit(BaseModel):
    display: str | None = Field(default=None, min_length=2, max_length=300)
    performed_on: date | None = None
    status: Literal["COMPLETED", "ABANDONED"] | None = None
    body_site: str | None = Field(default=None, max_length=120)
    outcome: str | None = Field(default=None, max_length=500)
    complications: str | None = Field(default=None, max_length=500)


class ProcedureOut(FactOut):
    display: str
    code: str | None
    code_system: str | None
    status: str
    performed_on: date
    body_site: str | None
    outcome: str | None
    complications: str | None


class ImmunisationIn(_Coded):
    vaccine: str = Field(min_length=2, max_length=200)
    given_on: date
    dose_number: int | None = Field(default=None, ge=1, le=20)
    given_here: bool = True
    batch_number: str | None = Field(default=None, max_length=60)
    site: str | None = Field(default=None, max_length=60)
    next_due_on: date | None = None
    note: str | None = Field(default=None, max_length=300)
    source: ClientSource | None = None

    @model_validator(mode="after")
    def _dates(self) -> "ImmunisationIn":
        _not_future(self.given_on, "The date given")
        if self.next_due_on is not None and self.next_due_on <= self.given_on:
            raise ValueError("The next dose must be due after this one")
        return self


class ImmunisationEdit(BaseModel):
    dose_number: int | None = Field(default=None, ge=1, le=20)
    given_on: date | None = None
    batch_number: str | None = Field(default=None, max_length=60)
    site: str | None = Field(default=None, max_length=60)
    next_due_on: date | None = None
    note: str | None = Field(default=None, max_length=300)


class ImmunisationOut(FactOut):
    vaccine: str
    code: str | None
    code_system: str | None
    dose_number: int | None
    given_on: date
    given_here: bool
    batch_number: str | None
    site: str | None
    next_due_on: date | None
    note: str | None


Urgency = Literal["ROUTINE", "URGENT", "EMERGENCY"]
ReferralStatus = Literal["REQUESTED", "ACCEPTED", "COMPLETED", "DECLINED", "CANCELLED"]
_CLOSED = {"COMPLETED", "DECLINED", "CANCELLED"}


class ReferralIn(BaseModel):
    to_specialty: str = Field(min_length=2, max_length=120)
    to_name: str | None = Field(default=None, max_length=200)
    reason: str = Field(min_length=3, max_length=500)
    urgency: Urgency = "ROUTINE"
    source: ClientSource | None = None


class ReferralEdit(BaseModel):
    to_name: str | None = Field(default=None, max_length=200)
    reason: str | None = Field(default=None, min_length=3, max_length=500)
    urgency: Urgency | None = None
    status: ReferralStatus | None = None
    outcome_note: str | None = Field(default=None, max_length=500)


class ReferralOut(FactOut):
    to_specialty: str
    to_name: str | None
    reason: str
    urgency: str
    status: str
    outcome_note: str | None


class PatientHistory(BaseModel):
    procedures: list[ProcedureOut]
    immunisations: list[ImmunisationOut]
    referrals: list[ReferralOut]


def _org(principal: Principal) -> uuid.UUID:
    assert principal.org_id is not None
    return principal.org_id


def _note(
    session: Session,
    principal: Principal,
    kind: str,
    row: Any,
    event: str,
    extra: dict[str, object],
) -> None:
    org_id = _org(principal)
    emit_event(
        session,
        org_id=org_id,
        event_type=event,
        aggregate_type=kind,
        aggregate_id=row.id,
        patient_id=row.patient_id,
        encounter_id=row.encounter_id,
        actor_user_id=principal.user_id,
        payload=extra,
    )
    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action=event,
        resource_type=kind,
        resource_id=row.id,
        after=extra,
    )


def _create(
    session: Session,
    principal: Principal,
    encounter_id: uuid.UUID,
    model: Any,
    kind: str,
    event: str,
    values: dict[str, Any],
) -> Any:
    enc = open_encounter(session, encounter_id)
    source = values.pop("source", None)
    row = model(
        organisation_id=_org(principal),
        patient_id=enc.patient_id,
        encounter_id=enc.id,
        **values,
        **provenance_for_new(principal, source),
    )
    session.add(row)
    session.flush()
    _note(session, principal, kind, row, event, {"kind": kind})
    session.commit()
    return row


def _correct(
    session: Session,
    principal: Principal,
    model: Any,
    fact_id: uuid.UUID,
    kind: str,
    event: str,
    changes: dict[str, Any],
) -> Any:
    old: Any = get_fact(session, model, fact_id)
    if not changes:
        raise AppError("Nothing to change")
    if kind == "referrals" and old.status in _CLOSED and old.status != changes.get("status"):
        raise AppError("A closed referral cannot be changed: start a new one")
    new = supersede(session, principal, old, changes)
    _note(session, principal, kind, new, event, {"kind": kind})
    session.commit()
    return new


def history_for(session: Session, patient_id: uuid.UUID) -> PatientHistory:
    def rows(model: Any, order: Any) -> list[Any]:
        q = select(model).where(model.patient_id == patient_id, *current_filter(model))
        return list(session.scalars(q.order_by(order.desc())))

    return PatientHistory(
        procedures=[
            ProcedureOut.model_validate(r)
            for r in rows(ProcedureRecord, ProcedureRecord.performed_on)
        ],
        immunisations=[
            ImmunisationOut.model_validate(r) for r in rows(Immunisation, Immunisation.given_on)
        ],
        referrals=[ReferralOut.model_validate(r) for r in rows(Referral, Referral.recorded_at)],
    )


# ---- routes ------------------------------------------------------------------------

Proc = Annotated[Principal, Depends(require("procedure:record"))]
Imm = Annotated[Principal, Depends(require("immunisation:record"))]
Ref = Annotated[Principal, Depends(require("referral:write"))]


@router.get("/patients/{patient_id}/history", response_model=PatientHistory)
def patient_history(
    patient_id: uuid.UUID,
    db: TenantDb,
    _: Annotated[Principal, Depends(require("patient:clinical"))],
) -> PatientHistory:
    return history_for(db, patient_id)


@router.post("/encounters/{encounter_id}/procedures", response_model=ProcedureOut, status_code=201)
def add_procedure(encounter_id: uuid.UUID, body: ProcedureIn, db: TenantDb, principal: Proc) -> Any:
    return _create(
        db, principal, encounter_id, ProcedureRecord, "procedures", "PROCEDURE_RECORDED",
        body.model_dump(),
    )  # fmt: skip


@router.put("/procedures/{fact_id}", response_model=ProcedureOut)
def edit_procedure(fact_id: uuid.UUID, body: ProcedureEdit, db: TenantDb, principal: Proc) -> Any:
    return _correct(
        db, principal, ProcedureRecord, fact_id, "procedures", "PROCEDURE_CORRECTED",
        body.model_dump(exclude_unset=True),
    )  # fmt: skip


@router.post(
    "/encounters/{encounter_id}/immunisations", response_model=ImmunisationOut, status_code=201
)
def add_immunisation(
    encounter_id: uuid.UUID, body: ImmunisationIn, db: TenantDb, principal: Imm
) -> Any:
    return _create(
        db, principal, encounter_id, Immunisation, "immunisations", "IMMUNISATION_RECORDED",
        body.model_dump(),
    )  # fmt: skip


@router.put("/immunisations/{fact_id}", response_model=ImmunisationOut)
def edit_immunisation(
    fact_id: uuid.UUID, body: ImmunisationEdit, db: TenantDb, principal: Imm
) -> Any:
    return _correct(
        db, principal, Immunisation, fact_id, "immunisations", "IMMUNISATION_CORRECTED",
        body.model_dump(exclude_unset=True),
    )  # fmt: skip


@router.post("/encounters/{encounter_id}/referrals", response_model=ReferralOut, status_code=201)
def add_referral(encounter_id: uuid.UUID, body: ReferralIn, db: TenantDb, principal: Ref) -> Any:
    return _create(
        db, principal, encounter_id, Referral, "referrals", "REFERRAL_CREATED", body.model_dump()
    )


@router.put("/referrals/{fact_id}", response_model=ReferralOut)
def update_referral(fact_id: uuid.UUID, body: ReferralEdit, db: TenantDb, principal: Ref) -> Any:
    return _correct(
        db, principal, Referral, fact_id, "referrals", "REFERRAL_UPDATED",
        body.model_dump(exclude_unset=True),
    )  # fmt: skip
