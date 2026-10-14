import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.context import Principal
from app.core.deps import TenantDb, require
from app.modules.consent import service
from app.modules.consent.schemas import (
    ConsentIn,
    ConsentOut,
    PatientConsents,
    PolicyIn,
    PolicyOut,
    WithdrawIn,
)

router = APIRouter(tags=["consent"])


@router.post("/consent-policies", response_model=PolicyOut, status_code=201)
def publish_policy(
    body: PolicyIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("consent:manage"))],
) -> PolicyOut:
    return PolicyOut.model_validate(service.create_policy(db, principal, body))


@router.post("/consent-policies/install-templates", response_model=list[PolicyOut], status_code=201)
def install_templates(
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("consent:manage"))],
    language: Annotated[str, Query(max_length=35)] = "en-IN",
) -> list[PolicyOut]:
    return [PolicyOut.model_validate(p) for p in service.install_templates(db, principal, language)]


@router.get("/consent-policies", response_model=list[PolicyOut])
def list_policies(
    db: TenantDb,
    _: Annotated[Principal, Depends(require("consent:policy"))],
    include_retired: bool = False,
) -> list[PolicyOut]:
    return [PolicyOut.model_validate(p) for p in service.list_policies(db, include_retired)]


@router.get("/patients/{patient_id}/consents", response_model=PatientConsents)
def patient_consents(
    patient_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("consent:read"))],
) -> PatientConsents:
    return service.patient_consents(db, principal, patient_id)


@router.post("/patients/{patient_id}/consents", response_model=ConsentOut, status_code=201)
def capture_consent(
    patient_id: uuid.UUID,
    body: ConsentIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("consent:capture"))],
) -> ConsentOut:
    return service.capture_consent(db, principal, patient_id, body)


@router.post("/consents/{consent_id}/withdraw", response_model=ConsentOut)
def withdraw_consent(
    consent_id: uuid.UUID,
    body: WithdrawIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("consent:withdraw"))],
) -> ConsentOut:
    return service.withdraw_consent(db, principal, consent_id, body.reason)
