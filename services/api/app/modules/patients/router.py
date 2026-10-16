import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.context import Principal
from app.core.deps import CryptoDep, TenantDb, require
from app.core.ratelimit import limiter_of
from app.modules.patients import service
from app.modules.patients.schemas import (
    IdentifierIn,
    IdentifierOut,
    PatientCreate,
    PatientHit,
    PatientOut,
    PatientUpdate,
    RevealedIdentifier,
    TimelineEvent,
)

router = APIRouter(prefix="/patients", tags=["patients"])


@router.post("", response_model=PatientOut, status_code=201)
def create_patient(
    body: PatientCreate,
    db: TenantDb,
    crypto: CryptoDep,
    principal: Annotated[Principal, Depends(require("patient:create"))],
) -> PatientOut:
    return service.create_patient(db, principal, crypto, body)


# Declared before "/{patient_id}" so "search" is never parsed as an id.
@router.get("/search", response_model=list[PatientHit])
def search_patients(
    db: TenantDb,
    request: Request,
    principal: Annotated[Principal, Depends(require("patient:search"))],
    name: Annotated[str | None, Query(max_length=100)] = None,
    mobile: Annotated[str | None, Query(max_length=20)] = None,
    mrn: Annotated[str | None, Query(max_length=20)] = None,
) -> list[PatientHit]:
    limiter_of(request).check(
        f"search:{principal.user_id}",
        limit=request.app.state.settings.patient_searches_per_minute_per_user,
        window_seconds=60,
    )
    return service.search_patients(db, principal, name=name, mobile=mobile, mrn=mrn)


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(
    patient_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("patient:read"))],
) -> PatientOut:
    return service.get_patient(db, principal, patient_id)


@router.patch("/{patient_id}", response_model=PatientOut)
def update_patient(
    patient_id: uuid.UUID,
    body: PatientUpdate,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("patient:update"))],
) -> PatientOut:
    return service.update_patient(db, principal, patient_id, body)


@router.post("/{patient_id}/identifiers", response_model=IdentifierOut, status_code=201)
def add_identifier(
    patient_id: uuid.UUID,
    body: IdentifierIn,
    db: TenantDb,
    crypto: CryptoDep,
    principal: Annotated[Principal, Depends(require("patient:update"))],
) -> IdentifierOut:
    return service.add_identifier(db, principal, crypto, patient_id, body)


@router.post("/{patient_id}/identifiers/{identifier_id}/reveal", response_model=RevealedIdentifier)
def reveal_identifier(
    patient_id: uuid.UUID,
    identifier_id: uuid.UUID,
    db: TenantDb,
    crypto: CryptoDep,
    principal: Annotated[Principal, Depends(require("patient:identifier"))],
) -> RevealedIdentifier:
    return service.reveal_identifier(db, principal, crypto, patient_id, identifier_id)


@router.get("/{patient_id}/timeline", response_model=list[TimelineEvent])
def timeline(
    patient_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("patient:timeline"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TimelineEvent]:
    return service.timeline(db, principal, patient_id, limit, offset)
