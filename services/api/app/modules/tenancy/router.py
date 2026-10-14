import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.context import Principal
from app.core.deps import TenantDb, require
from app.modules.tenancy import service
from app.modules.tenancy.schemas import (
    DepartmentCreate,
    DepartmentOut,
    FacilityCreate,
    FacilityOut,
    FacilityUpdate,
    OrganisationCreate,
    OrganisationOut,
)

router = APIRouter(tags=["tenancy"])


@router.post("/organisations", response_model=OrganisationOut, status_code=201)
def create_organisation(
    body: OrganisationCreate,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("platform:organisations"))],
) -> OrganisationOut:
    return OrganisationOut.model_validate(service.create_organisation(db, principal, body))


@router.get("/organisations", response_model=list[OrganisationOut])
def list_organisations(
    db: TenantDb, _: Annotated[Principal, Depends(require("platform:organisations"))]
) -> list[OrganisationOut]:
    return [OrganisationOut.model_validate(o) for o in service.list_organisations(db)]


@router.get("/organisations/current", response_model=OrganisationOut)
def current_organisation(
    db: TenantDb, principal: Annotated[Principal, Depends(require("org:read"))]
) -> OrganisationOut:
    return OrganisationOut.model_validate(service.current_organisation(db, principal))


@router.get("/facilities", response_model=list[FacilityOut])
def list_facilities(
    db: TenantDb, principal: Annotated[Principal, Depends(require("facility:read"))]
) -> list[FacilityOut]:
    return [FacilityOut.model_validate(f) for f in service.list_facilities(db, principal)]


@router.post("/facilities", response_model=FacilityOut, status_code=201)
def create_facility(
    body: FacilityCreate,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("facility:manage"))],
) -> FacilityOut:
    return FacilityOut.model_validate(service.create_facility(db, principal, body))


@router.get("/facilities/{facility_id}", response_model=FacilityOut)
def get_facility(
    facility_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("facility:read"))],
) -> FacilityOut:
    return FacilityOut.model_validate(service.get_facility(db, principal, facility_id))


@router.patch("/facilities/{facility_id}", response_model=FacilityOut)
def update_facility(
    facility_id: uuid.UUID,
    body: FacilityUpdate,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("facility:manage"))],
) -> FacilityOut:
    return FacilityOut.model_validate(service.update_facility(db, principal, facility_id, body))


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("department:read"))],
    facility_id: uuid.UUID | None = None,
) -> list[DepartmentOut]:
    return [
        DepartmentOut.model_validate(d)
        for d in service.list_departments(db, principal, facility_id)
    ]


@router.post("/departments", response_model=DepartmentOut, status_code=201)
def create_department(
    body: DepartmentCreate,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("department:manage"))],
) -> DepartmentOut:
    return DepartmentOut.model_validate(service.create_department(db, principal, body))
