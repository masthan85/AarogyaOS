import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.ai.knowledge import NotAvailable
from app.ai.services import get_translator, get_tts
from app.core.context import Principal
from app.core.deps import SettingsDep, TenantDb, require
from app.core.errors import ServiceUnavailable
from app.modules.ai.schemas import LetterDraftIn, SummaryDraftIn, SummaryEditIn, SummaryOut
from app.modules.summaries import service

router = APIRouter(tags=["patient-summary"])


@router.post("/encounters/{encounter_id}/summaries", response_model=SummaryOut, status_code=201)
def draft(
    encounter_id: uuid.UUID,
    body: SummaryDraftIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("summary:write"))],
    settings: SettingsDep,
) -> SummaryOut:
    return service.draft(db, principal, encounter_id, body, get_translator(settings))


@router.post("/encounters/{encounter_id}/letters", response_model=SummaryOut, status_code=201)
def draft_letter(
    encounter_id: uuid.UUID,
    body: LetterDraftIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("summary:write"))],
) -> SummaryOut:
    return service.draft_letter(db, principal, encounter_id, body)


@router.get("/encounters/{encounter_id}/summaries", response_model=list[SummaryOut])
def list_summaries(
    encounter_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("summary:read"))],
) -> list[SummaryOut]:
    return service.list_for_encounter(db, principal, encounter_id)


@router.put("/summaries/{summary_id}", response_model=SummaryOut)
def edit(
    summary_id: uuid.UUID,
    body: SummaryEditIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("summary:write"))],
) -> SummaryOut:
    return service.edit(db, principal, summary_id, body.content)


@router.post("/summaries/{summary_id}/approve", response_model=SummaryOut)
def approve(
    summary_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("summary:write"))],
) -> SummaryOut:
    return service.approve(db, principal, summary_id)


@router.post("/summaries/{summary_id}/speech")
def speech(
    summary_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("summary:read"))],
    settings: SettingsDep,
) -> Response:
    try:
        tts = get_tts(settings)
        audio = service.speak(db, principal, settings, summary_id, tts)
    except (NotAvailable, service.SpeechUnavailable) as exc:
        raise ServiceUnavailable(str(exc)) from exc
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})
