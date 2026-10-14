"""Authenticated audio WebSocket: phone microphone -> speech provider -> stored transcript.

Protocol (all control messages are JSON text; audio is binary PCM, 16 kHz mono s16le):
  client -> {"type": "auth", "token": "<access token>"}      first message, within 5 seconds
  server -> {"type": "ready", "format": {...}}
  client -> <binary audio frames, each <= 64 KiB, even length>
  client -> {"type": "stop"}                                  ends and closes the session
  server -> {"type": "stopped", "reason": "..."}              then closes with a 4xxx code

Close codes: 4401 not authenticated, 4403 not allowed (incl. consent), 4404 unknown session,
4409 session not active / already connected, 4001 session ended or consent withdrawn,
4002 time limit reached, 4503 speech service unavailable, 1011 provider failure.
The gateway re-checks the session and the patient's consent on a timer while audio flows, so a
withdrawal stops the stream within one interval. A dropped connection pauses the session: the
app must never display 'recording' for audio that is not being captured.
"""

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from typing import Any

import anyio
from anyio import to_thread
from fastapi import APIRouter, FastAPI, WebSocket
from sqlalchemy import func, select

from app.core.context import Principal, RequestMeta
from app.core.db import set_tenant
from app.core.deps import build_principal
from app.core.errors import NotFound, Unauthorized
from app.core.security import InvalidToken, decode_access_token
from app.modules.consent.queries import missing_consents
from app.modules.interactions import service
from app.modules.interactions.models import AudioAsset, TranscriptSegment
from app.modules.interactions.schemas import AudioFormat
from app.modules.tenancy.policy import load_policy
from app.speech import live
from app.speech.pipeline import StreamFailed, run_stream
from app.speech.provider import (
    BYTES_PER_SECOND,
    ProviderNotAvailable,
    ProviderStats,
    RecognisedSegment,
    SpeechProvider,
    StreamOptions,
)
from app.speech.registry import get_provider

log = logging.getLogger("aarogya.gateway")
router = APIRouter(tags=["recording"])

MAX_FRAME_BYTES = AudioFormat().max_frame_bytes
AUTH_TIMEOUT_SECONDS = 5.0
_connected: set[uuid.UUID] = set()  # one live connection per session (per process)


class Refusal(Exception):
    def __init__(self, code: int, reason: str) -> None:
        super().__init__(reason)
        self.code, self.reason = code, reason


@dataclass
class Flags:
    client_stopped: bool = False
    limit: bool = False
    server_stop: str | None = None
    bytes: int = 0
    fresh: bool = False  # audio arrived since the last monitor tick


@dataclass
class Ctx:
    principal: Principal
    interaction_id: uuid.UUID
    patient_id: uuid.UUID
    language_hint: str
    primary: SpeechProvider
    fallback: SpeechProvider | None
    retain_audio: bool
    storage_key: str | None
    first_seq: int
    offset_ms: int
    asset_id: uuid.UUID | None


def _run(fn: Any, *args: Any) -> Any:
    return to_thread.run_sync(fn, *args)


def _authenticate(app: FastAPI, token: str, interaction_id: uuid.UUID, host: str | None) -> Ctx:
    settings = app.state.settings
    try:
        claims = decode_access_token(settings, token)
    except InvalidToken as exc:
        raise Refusal(4401, "invalid token") from exc
    with app.state.sessionmaker() as db:
        set_tenant(db, claims.org_id, platform=claims.org_id is None)
        try:
            principal = build_principal(db, claims, RequestMeta(host, "audio-gateway", None))
        except Unauthorized as exc:
            raise Refusal(4401, "not authenticated") from exc
        if principal.org_id is None:
            raise Refusal(4403, "not allowed")
        try:
            ia = service.visible(db, principal, interaction_id)
        except NotFound as exc:
            raise Refusal(4404, "unknown session") from exc
        if ia.started_by != principal.user_id or not principal.has(
            service.PURPOSE_PERMISSION[ia.purpose]
        ):
            raise Refusal(4403, "not allowed")
        if ia.status != "ACTIVE":
            raise Refusal(4409, f"session is {ia.status.lower()}")
        if not load_policy(db, principal.org_id).recording_enabled:
            raise Refusal(4403, "recording disabled")
        if missing_consents(db, ia.patient_id, service.required_purposes(ia.ai_processing)):
            raise Refusal(4403, "consent missing")
        try:
            primary = get_provider(settings.speech_provider, environment=settings.environment)
        except ProviderNotAvailable as exc:
            raise Refusal(4503, "speech service unavailable") from exc
        fallback = None
        if settings.speech_fallback_provider:
            try:
                fallback = get_provider(
                    settings.speech_fallback_provider, environment=settings.environment
                )
            except ProviderNotAvailable:
                log.warning("fallback speech provider unavailable")
        seq, end_ms = db.execute(
            select(
                func.coalesce(func.max(TranscriptSegment.seq), 0),
                func.coalesce(func.max(TranscriptSegment.end_ms), 0),
            ).where(TranscriptSegment.interaction_id == ia.id)
        ).one()
        asset_id = key = None
        if ia.retain_audio:
            asset = db.scalar(
                select(AudioAsset).where(
                    AudioAsset.interaction_id == ia.id, AudioAsset.deleted_at.is_(None)
                )
            )
            if asset is None:
                key = f"{principal.org_id}/{ia.id}.audio"
                asset = AudioAsset(
                    organisation_id=principal.org_id,
                    interaction_id=ia.id,
                    patient_id=ia.patient_id,
                    storage_key=key,
                )
                db.add(asset)
                db.commit()
            asset_id, key = asset.id, asset.storage_key
        return Ctx(
            principal,
            ia.id,
            ia.patient_id,
            ia.language_hint,
            primary,
            fallback,
            ia.retain_audio,
            key,
            int(seq) + 1,
            int(end_ms),
            asset_id,
        )


def _persist(
    app: FastAPI, ctx: Ctx, seg: RecognisedSegment, seq: int, provider: SpeechProvider
) -> None:
    from datetime import UTC, datetime

    with app.state.sessionmaker() as db:
        set_tenant(db, ctx.principal.org_id)
        ia = service.get_interaction(db, ctx.interaction_id)
        shifted = replace(
            seg, start_ms=seg.start_ms + ctx.offset_ms, end_ms=seg.end_ms + ctx.offset_ms
        )
        service.add_segment(db, ia, shifted, seq, provider)
        ia.last_audio_at = datetime.now(UTC)
        db.commit()


def _check(app: FastAPI, ctx: Ctx, got_audio: bool) -> str | None:
    """Return a reason to stop, or None to continue. Runs on a timer while audio flows."""
    from datetime import UTC, datetime

    with app.state.sessionmaker() as db:
        set_tenant(db, ctx.principal.org_id)
        ia = service.get_interaction(db, ctx.interaction_id)
        if ia.status != "ACTIVE":
            return ia.end_reason or ia.pause_reason or ia.status
        if missing_consents(db, ia.patient_id, service.required_purposes(ia.ai_processing)):
            service.stop(db, ctx.principal, ia.id, "CONSENT_WITHDRAWN")
            return "CONSENT_WITHDRAWN"
        if got_audio:
            ia.last_audio_at = datetime.now(UTC)
            db.commit()
    return None


def _finish(
    app: FastAPI,
    ctx: Ctx,
    stats: ProviderStats,
    *,
    client_stopped: bool,
    failed: bool,
    limit_hit: bool,
    stop_reason: str | None,
    bytes_written: int,
) -> None:
    with app.state.sessionmaker() as db:
        set_tenant(db, ctx.principal.org_id)
        ia = service.get_interaction(db, ctx.interaction_id, lock=True)
        service.record_usage(db, ia, stats)
        if ctx.asset_id is not None:
            asset = db.get(AudioAsset, ctx.asset_id)
            if asset is not None:
                asset.bytes += bytes_written
                asset.duration_ms += int(bytes_written / BYTES_PER_SECOND * 1000)
                db.commit()
        if client_stopped:
            service.stop(db, ctx.principal, ia.id, "USER")
        elif ia.status == "ACTIVE":
            reason = (
                "PROVIDER_ERROR"
                if failed
                else "MAX_DURATION"
                if limit_hit
                else stop_reason or "CONNECTION_LOST"
            )
            service.pause_system(db, ctx.principal, ia, reason)


async def _close(ws: WebSocket, code: int, reason: str) -> None:
    with contextlib.suppress(Exception):  # the peer may already be gone
        await ws.send_json({"type": "stopped", "reason": reason})
        await ws.close(code=code)


@router.websocket("/interactions/{interaction_id}/audio")
async def audio_gateway(ws: WebSocket, interaction_id: uuid.UUID) -> None:
    app: FastAPI = ws.app
    await ws.accept()
    try:
        first = await asyncio.wait_for(ws.receive_json(), AUTH_TIMEOUT_SECONDS)
        if (
            not isinstance(first, dict)
            or first.get("type") != "auth"
            or not isinstance(first.get("token"), str)
        ):
            raise Refusal(4401, "send an auth message first")
        ctx: Ctx = await _run(
            _authenticate,
            app,
            first["token"],
            interaction_id,
            ws.client.host if ws.client else None,
        )
    except Refusal as r:
        return await _close(ws, r.code, r.reason)
    except (TimeoutError, ValueError, KeyError, RuntimeError):
        return await _close(ws, 4401, "authentication required")
    except Exception:  # noqa: BLE001
        log.exception("gateway authentication failed")
        return await _close(ws, 1011, "internal error")

    if interaction_id in _connected:
        return await _close(ws, 4409, "already connected")
    _connected.add(interaction_id)
    try:
        await ws.send_json({"type": "ready", "format": AudioFormat().model_dump()})
        await _stream(app, ws, ctx)
    finally:
        _connected.discard(interaction_id)


async def _stream(app: FastAPI, ws: WebSocket, ctx: Ctx) -> None:
    settings = app.state.settings
    store = app.state.audio_store
    writer = store.writer(ctx.storage_key) if ctx.storage_key else None
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=256)
    flags = Flags()
    max_bytes = settings.speech_max_session_seconds * BYTES_PER_SECOND
    seq = ctx.first_seq
    stats = ProviderStats(ctx.primary.name, ctx.primary.model)
    failed = False

    async def reader() -> None:
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if (data := msg.get("bytes")) is not None:
                    if len(data) > MAX_FRAME_BYTES or len(data) % 2:
                        flags.server_stop = "BAD_FRAME"
                        break
                    flags.bytes += len(data)
                    flags.fresh = True
                    if flags.bytes > max_bytes:
                        flags.limit = True
                        break
                    if writer is not None:
                        writer.append(data)
                    await queue.put(data)
                elif (text := msg.get("text")) is not None:
                    kind = _kind(text)
                    if kind == "stop":
                        flags.client_stopped = True
                        break
                    if kind == "ping":
                        await ws.send_json({"type": "pong"})
        except RuntimeError:
            pass  # socket already closed
        finally:
            await queue.put(None)

    async def monitor() -> None:
        while True:
            await asyncio.sleep(settings.speech_monitor_interval_seconds)
            reason = await _run(_check, app, ctx, flags.fresh)
            flags.fresh = False
            if reason:
                flags.server_stop = reason
                await queue.put(None)
                return

    async def audio() -> AsyncIterator[bytes]:
        while (frame := await queue.get()) is not None:
            yield frame

    async def on_partial(seg: RecognisedSegment) -> None:
        live.set_partial(
            ctx.interaction_id, live.LivePartial(seg.text, seg.speaker_id, seg.language)
        )

    async def on_final(seg: RecognisedSegment, provider: SpeechProvider) -> None:
        nonlocal seq
        current, seq = seq, seq + 1
        await _run(_persist, app, ctx, seg, current, provider)
        live.clear(ctx.interaction_id)

    tasks = [asyncio.create_task(reader()), asyncio.create_task(monitor())]
    try:
        opts = StreamOptions(language_hint=ctx.language_hint)
        stats = await run_stream(ctx.primary, ctx.fallback, audio(), opts, on_partial, on_final)
    except StreamFailed as exc:
        failed, stats = True, exc.stats
        log.error("speech provider failed", extra={"path": type(exc.cause).__name__})
    finally:
        # Shielded: even if this task is cancelled (server shutdown, a hung-up client), the
        # session must still be paused and its usage recorded, or the app would go on
        # displaying "recording" for audio that is no longer being captured.
        with anyio.CancelScope(shield=True):
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if writer is not None:
                writer.close()
            live.clear(ctx.interaction_id)
            await _run(
                lambda: _finish(
                    app,
                    ctx,
                    stats,
                    client_stopped=flags.client_stopped,
                    failed=failed,
                    limit_hit=flags.limit,
                    stop_reason=flags.server_stop,
                    bytes_written=flags.bytes,
                )
            )

    if failed:
        await _close(ws, 1011, "speech provider failed")
    elif flags.limit:
        await _close(ws, 4002, "MAX_DURATION")
    elif flags.server_stop:
        await _close(ws, 4001, str(flags.server_stop))
    elif flags.client_stopped:
        await _close(ws, 1000, "USER")
    else:
        with contextlib.suppress(Exception):
            await ws.close(code=1000)


def _kind(text: str) -> str | None:
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return str(value.get("type")) if isinstance(value, dict) else None
