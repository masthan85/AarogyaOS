import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.context import Principal
from app.core.deps import TenantDb, require
from app.modules.retention import service
from app.modules.retention.service import HoldIn, HoldOut

router = APIRouter(tags=["retention"])
Manager = Annotated[Principal, Depends(require("legalhold:manage"))]
Reader = Annotated[Principal, Depends(require("legalhold:read"))]


@router.get("/legal-holds", response_model=list[HoldOut])
def list_holds(
    db: TenantDb, _: Reader, patient_id: uuid.UUID | None = None, all: bool = False
) -> list[HoldOut]:
    return service.list_holds(db, patient_id=patient_id, active_only=not all)


@router.post("/patients/{patient_id}/legal-holds", response_model=HoldOut, status_code=201)
def place_hold(patient_id: uuid.UUID, body: HoldIn, db: TenantDb, principal: Manager) -> HoldOut:
    return service.place(db, principal, patient_id, body)


@router.post("/legal-holds/{hold_id}/release", response_model=HoldOut)
def release_hold(hold_id: uuid.UUID, body: HoldIn, db: TenantDb, principal: Manager) -> HoldOut:
    return service.release(db, principal, hold_id, body)
