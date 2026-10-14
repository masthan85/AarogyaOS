import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.context import Principal
from app.core.deps import TenantDb, require
from app.core.errors import AppError
from app.modules.interop import fhir, service

router = APIRouter(prefix="/fhir", tags=["fhir"])
Export = Annotated[Principal, Depends(require("fhir:export"))]

_ISSUE = {400: "invalid", 403: "forbidden", 404: "not-found", 409: "conflict", 429: "throttled"}


def _fhir(body: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status, media_type=fhir.JSON_TYPE)


def _outcome(exc: AppError) -> JSONResponse:
    return _fhir(
        {
            "resourceType": "OperationOutcome",
            "issue": [
                {
                    "severity": "error",
                    "code": _ISSUE.get(exc.status_code, "processing"),
                    "diagnostics": exc.detail,
                }
            ],
        },
        exc.status_code,
    )


@router.get("/metadata")
def metadata(request: Request, _: Export) -> JSONResponse:
    return _fhir(fhir.capability_statement(str(request.base_url) + "api/v1/fhir"))


@router.get("/Patient/{patient_id}")
def read_patient(patient_id: uuid.UUID, db: TenantDb, principal: Export) -> JSONResponse:
    try:
        return _fhir(service.patient_resource(db, principal, patient_id))
    except AppError as exc:
        return _outcome(exc)


@router.get("/Encounter/{encounter_id}")
def read_encounter(encounter_id: uuid.UUID, db: TenantDb, principal: Export) -> JSONResponse:
    try:
        return _fhir(service.encounter_resource(db, principal, encounter_id))
    except AppError as exc:
        return _outcome(exc)


@router.get("/Encounter/{encounter_id}/$export-document")
def export_document(encounter_id: uuid.UUID, db: TenantDb, principal: Export) -> JSONResponse:
    try:
        return _fhir(service.encounter_document(db, principal, encounter_id))
    except AppError as exc:
        return _outcome(exc)
