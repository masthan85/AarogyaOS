import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

from anyio import to_thread
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials

from app.core.context import Principal, RequestMeta
from app.core.db import set_tenant
from app.core.deps import PrincipalDep, SettingsDep, TenantDb, build_principal, get_claims, require
from app.modules.audit.service import record_audit
from app.modules.interactions import service
from app.modules.interactions.schemas import (
    AudioFormat,
    CorrectionIn,
    InteractionCreate,
    InteractionOut,
    SegmentOut,
    SpeakerAssign,
    SpeakerOut,
    StartOut,
    StopIn,
    TranscriptOut,
    UsageRow,
)

router = APIRouter(tags=["recording"])


@router.post("/interactions", response_model=InteractionOut, status_code=201)
def create_interaction(
    body: InteractionCreate, db: TenantDb, principal: PrincipalDep, settings: SettingsDep
) -> InteractionOut:
    return InteractionOut.model_validate(service.create_interaction(db, principal, settings, body))


@router.post("/interactions/{interaction_id}/start", response_model=StartOut)
def start(interaction_id: uuid.UUID, db: TenantDb, principal: PrincipalDep) -> StartOut:
    ia = service.start(db, principal, interaction_id)
    return StartOut(
        interaction=InteractionOut.model_validate(ia),
        gateway_path=f"/api/v1/interactions/{ia.id}/audio",
        audio_format=AudioFormat(),
    )


@router.post("/interactions/{interaction_id}/pause", response_model=InteractionOut)
def pause(interaction_id: uuid.UUID, db: TenantDb, principal: PrincipalDep) -> InteractionOut:
    return InteractionOut.model_validate(service.pause(db, principal, interaction_id))


@router.post("/interactions/{interaction_id}/resume", response_model=InteractionOut)
def resume(interaction_id: uuid.UUID, db: TenantDb, principal: PrincipalDep) -> InteractionOut:
    return InteractionOut.model_validate(service.resume(db, principal, interaction_id))


@router.post("/interactions/{interaction_id}/stop", response_model=InteractionOut)
def stop(
    interaction_id: uuid.UUID, body: StopIn, db: TenantDb, principal: PrincipalDep
) -> InteractionOut:
    return InteractionOut.model_validate(service.stop(db, principal, interaction_id, body.reason))


@router.get("/interactions/{interaction_id}", response_model=InteractionOut)
def get_interaction(
    interaction_id: uuid.UUID, db: TenantDb, principal: PrincipalDep
) -> InteractionOut:
    ia = service.visible(db, principal, interaction_id)
    service.reconcile_stale(db, ia)
    return InteractionOut.model_validate(ia)


@router.get("/interactions/{interaction_id}/transcript", response_model=TranscriptOut)
def get_transcript(
    interaction_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("transcript:read"))],
    after_seq: Annotated[int, Query(ge=0)] = 0,
) -> TranscriptOut:
    return service.transcript(db, principal, interaction_id, after_seq)


@router.put(
    "/interactions/{interaction_id}/segments/{segment_id}/correction", response_model=SegmentOut
)
def correct_segment(
    interaction_id: uuid.UUID,
    segment_id: uuid.UUID,
    body: CorrectionIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("transcript:correct"))],
) -> SegmentOut:
    return service.correct_segment(db, principal, interaction_id, segment_id, body.text)


@router.put("/interactions/{interaction_id}/speakers/{speaker_id}", response_model=SpeakerOut)
def assign_speaker(
    interaction_id: uuid.UUID,
    speaker_id: str,
    body: SpeakerAssign,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("speaker:assign"))],
) -> SpeakerOut:
    return service.assign_speaker(db, principal, interaction_id, speaker_id, body.role, body.label)


@router.get("/patients/{patient_id}/interactions", response_model=list[InteractionOut])
def patient_interactions(
    patient_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("transcript:read"))],
) -> list[InteractionOut]:
    return [
        InteractionOut.model_validate(i)
        for i in service.list_for_patient(db, principal, patient_id)
    ]


@router.get("/usage/speech", response_model=list[UsageRow])
def speech_usage(
    db: TenantDb,
    _: Annotated[Principal, Depends(require("usage:read"))],
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[UsageRow]:
    end = until or datetime.now(UTC) + timedelta(minutes=1)
    return service.usage_summary(db, since or end - timedelta(days=30), end)


@router.get("/interactions/{interaction_id}/events")
async def transcript_events(interaction_id: uuid.UUID, request: Request) -> StreamingResponse:
    """Server-sent events for web/tablet clients. Mobile polls /transcript instead (see docs).

    Authorises once, then polls the database with short-lived sessions so that a slow viewer
    never holds a connection from the pool.
    """
    app = request.app
    auth = request.headers.get("authorization", "")
    claims = get_claims(app.state.settings, _bearer(auth))
    meta = RequestMeta.from_request(request)

    def authorise() -> Principal:
        with app.state.sessionmaker() as db:
            set_tenant(db, claims.org_id, platform=claims.org_id is None)
            principal = build_principal(db, claims, meta)
            if not principal.has("transcript:read"):
                from app.core.errors import Forbidden

                raise Forbidden("You cannot read transcripts")
            service.visible(db, principal, interaction_id)
            record_audit(
                db,
                meta,
                org_id=principal.org_id,
                actor_user_id=principal.user_id,
                action="TRANSCRIPT_VIEWED",
                resource_type="interaction",
                resource_id=interaction_id,
            )
            db.commit()
            return principal

    principal = await to_thread.run_sync(authorise)

    def fetch(after: int) -> TranscriptOut:
        with app.state.sessionmaker() as db:
            set_tenant(db, principal.org_id)
            return service.transcript(db, principal, interaction_id, after, audit_view=False)

    async def stream() -> AsyncIterator[str]:
        after = 0
        for _ in range(7200):  # hard cap: ~1 hour at 0.5 s
            data = await to_thread.run_sync(fetch, after)
            for seg in data.segments:
                after = seg.seq
                yield f"event: segment\ndata: {seg.model_dump_json()}\n\n"
            if data.status == "ENDED":
                yield f"event: end\ndata: {json.dumps({'status': data.status})}\n\n"
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"}
    )


def _bearer(header: str) -> HTTPAuthorizationCredentials | None:
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return HTTPAuthorizationCredentials(scheme=scheme, credentials=token)
