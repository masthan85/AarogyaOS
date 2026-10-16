import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.context import Principal
from app.core.deps import TenantDb, require
from app.modules.pharmacy import service
from app.modules.pharmacy.service import DispenseIn, DispensingOut

router = APIRouter(tags=["pharmacy"])


@router.post("/prescriptions/{rx_id}/dispensing", response_model=DispensingOut, status_code=201)
def dispense(
    rx_id: uuid.UUID,
    body: DispenseIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("prescription:dispense"))],
) -> DispensingOut:
    return service.record(db, principal, rx_id, body)


@router.get("/patients/{patient_id}/dispensings", response_model=list[DispensingOut])
def patient_dispensings(
    patient_id: uuid.UUID,
    db: TenantDb,
    _: Annotated[Principal, Depends(require("prescription:read"))],
) -> list[DispensingOut]:
    return service.for_patient(db, patient_id)
