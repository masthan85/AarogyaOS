"""The Sarvam adapter against a local fake server that speaks the SDK-documented protocol.

This proves the adapter follows that protocol (URL, header, query, message shapes, flush, error
handling). It does NOT prove the real service behaves the same: see scripts/sarvam_live_check.py.
"""

import asyncio
import base64
import json
import threading
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Response

from app.speech.provider import CapabilityNotSupported, ProviderError, StreamOptions
from app.speech.sarvam import SarvamSpeechProvider

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


SECOND = b"\x00\x00" * 16000
KEY = "sk-test-key-do-not-log"


class Fake:
    """Records what the adapter sent and replies from a script."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []
        self.on_audio: Callable[[int, ServerConnection], Any] | None = None
        self.on_flush: Callable[[ServerConnection], Any] | None = None
        self.refuse_with: int | None = None
        self.url = ""
        self.closed = threading.Event()


@pytest.fixture
def fake() -> Iterator[Fake]:
    state = Fake()
    ready = threading.Event()
    loop = asyncio.new_event_loop()

    async def handler(ws: ServerConnection) -> None:
        count = 0
        try:
            async for raw in ws:
                msg = json.loads(raw)
                state.messages.append(msg)
                if msg.get("type") == "flush":
                    if state.on_flush:
                        await state.on_flush(ws)
                elif "audio" in msg:
                    count += 1
                    if state.on_audio:
                        await state.on_audio(count, ws)
        except ConnectionClosed:
            pass
        finally:
            state.closed.set()

    def process_request(conn: ServerConnection, request: Any) -> Response | None:
        url = urlparse(request.path)
        state.requests.append(
            {
                "path": url.path,
                "query": {k: v[0] for k, v in parse_qs(url.query).items()},
                "key": request.headers.get("Api-Subscription-Key"),
            }
        )
        if state.refuse_with:
            return conn.respond(state.refuse_with, "refused")  # type: ignore[arg-type]
        return None

    async def run() -> None:
        async with serve(handler, "127.0.0.1", 0, process_request=process_request) as server:
            port = next(iter(server.sockets)).getsockname()[1]
            state.url = f"ws://127.0.0.1:{port}/speech-to-text/ws"
            ready.set()
            await asyncio.Event().wait()

    tasks: list[asyncio.Task[None]] = []

    def thread() -> None:
        asyncio.set_event_loop(loop)
        tasks.append(loop.create_task(run()))
        try:
            loop.run_until_complete(tasks[0])
        except asyncio.CancelledError:
            pass
        finally:
            loop.close()

    t = threading.Thread(target=thread, daemon=True)
    t.start()
    assert ready.wait(5)
    yield state
    loop.call_soon_threadsafe(tasks[0].cancel)
    t.join(5)


def provider(fake: Fake, **kw: Any) -> SarvamSpeechProvider:
    return SarvamSpeechProvider(KEY, url=fake.url, drain_seconds=0.4, **kw)


async def seconds(n: int) -> AsyncIterator[bytes]:
    for _ in range(n):
        yield SECOND
        await asyncio.sleep(0)


async def collect(p: SarvamSpeechProvider, audio: AsyncIterator[bytes], **kw: Any) -> list[Any]:
    return [s async for s in p.stream_transcribe(audio, StreamOptions(**kw))]


def data(text: str, *, lang: str = "hi-IN", prob: float | None = 0.9, dur: float = 2.0) -> str:
    return json.dumps(
        {
            "type": "data",
            "data": {
                "request_id": "r1",
                "transcript": text,
                "language_code": lang,
                "language_probability": prob,
                "metrics": {"audio_duration": dur, "processing_latency": 0.3},
            },
        }
    )


async def test_it_speaks_the_documented_protocol(fake: Fake) -> None:
    async def after_flush(ws: ServerConnection) -> None:
        await ws.send(data("मुझे तीन दिन से बुखार है"))

    fake.on_flush = after_flush
    segments = await collect(provider(fake), seconds(2), language_hint="hi-IN")

    req = fake.requests[0]
    assert req["path"] == "/speech-to-text/ws" and req["key"] == KEY
    assert req["query"] == {
        "language-code": "hi-IN",
        "model": "saaras:v4",
        "mode": "transcribe",
        "sample_rate": "16000",
        "input_audio_codec": "pcm_s16le",
        "vad_signals": "true",
        "flush_signal": "true",
    }
    audio_msgs = [m for m in fake.messages if "audio" in m]
    assert len(audio_msgs) == 2
    assert audio_msgs[0]["audio"] == {
        "data": base64.b64encode(SECOND).decode(),
        "sample_rate": 16000,
        "encoding": "audio/wav",
    }
    assert fake.messages[-1] == {"type": "flush"}  # flush comes after the last audio
    assert len(segments) == 1 and segments[0].is_final
    assert segments[0].text == "मुझे तीन दिन से बुखार है"
    assert segments[0].language == "hi-IN" and segments[0].language_confidence == 0.9


async def test_nothing_is_invented_that_the_service_does_not_provide(fake: Fake) -> None:
    async def after_flush(ws: ServerConnection) -> None:
        await ws.send(data("hello"))

    fake.on_flush = after_flush
    (seg,) = await collect(provider(fake), seconds(1))
    assert seg.speaker_id is None and seg.confidence is None  # no diarisation, no score
    assert seg.code_switch_spans == ()
    caps = provider(fake).capabilities
    assert caps.diarisation == "none" and not caps.word_timestamps and caps.streaming


async def test_segment_times_are_estimated_from_speech_start_and_reported_duration(
    fake: Fake,
) -> None:
    async def on_audio(n: int, ws: ServerConnection) -> None:
        if n == 2:  # speech starts after two seconds of audio have been sent
            await ws.send(json.dumps({"type": "events", "data": {"signal_type": "START_SPEECH"}}))
        if n == 4:
            await ws.send(data("one", dur=1.5))

    async def after_flush(ws: ServerConnection) -> None:
        await ws.send(data("two", dur=1.0))

    fake.on_audio, fake.on_flush = on_audio, after_flush
    segs = await collect(provider(fake), seconds(5))
    assert [s.text for s in segs] == ["one", "two"]
    assert segs[0].end_ms - segs[0].start_ms == 1500
    assert segs[0].start_ms >= 1000  # not before the speech start we observed
    assert segs[1].start_ms >= segs[0].end_ms  # monotonic, never overlapping


async def test_empty_transcripts_and_garbage_are_ignored(fake: Fake) -> None:
    async def after_flush(ws: ServerConnection) -> None:
        await ws.send(data("   "))
        await ws.send("not json")
        await ws.send(json.dumps([1, 2]))
        await ws.send(data("real"))

    fake.on_flush = after_flush
    assert [s.text for s in await collect(provider(fake), seconds(1))] == ["real"]


async def test_the_app_default_ignores_the_hint_and_lets_the_service_detect(fake: Fake) -> None:
    await collect(provider(fake, use_language_hint=False), seconds(1), language_hint="hi-IN")
    assert fake.requests[0]["query"]["language-code"] == "unknown"


async def test_language_hints_the_service_does_not_support_become_auto_detect(fake: Fake) -> None:
    for hint in ("auto", "xx-YY", "en-GB"):
        fake.requests.clear()
        await collect(provider(fake), seconds(1), language_hint=hint)
        assert fake.requests[0]["query"]["language-code"] == "unknown"


async def test_a_vendor_error_surfaces_its_code_but_never_its_text_or_the_key(fake: Fake) -> None:
    async def on_audio(n: int, ws: ServerConnection) -> None:
        await ws.send(
            json.dumps(
                {
                    "type": "error",
                    "data": {
                        "error": "could not process: patient has chest pain",
                        "code": "rate_limit_exceeded_error",
                    },
                }
            )
        )

    fake.on_audio = on_audio
    with pytest.raises(ProviderError) as exc:
        await collect(provider(fake), seconds(2))
    assert "rate_limit_exceeded_error" in str(exc.value)
    assert "chest pain" not in str(exc.value) and KEY not in str(exc.value)


async def test_a_refused_connection_is_a_provider_error_without_the_key(fake: Fake) -> None:
    fake.refuse_with = 401
    with pytest.raises(ProviderError) as exc:
        await collect(provider(fake), seconds(1))
    assert "401" in str(exc.value) and KEY not in str(exc.value)


async def test_an_unreachable_server_is_a_provider_error() -> None:
    p = SarvamSpeechProvider(KEY, url="ws://127.0.0.1:1/speech-to-text/ws", drain_seconds=0.1)
    with pytest.raises(ProviderError):
        await collect(p, seconds(1))


async def test_cancelling_closes_the_connection(fake: Fake) -> None:
    async def endless() -> AsyncIterator[bytes]:
        while True:
            yield SECOND
            await asyncio.sleep(0.05)

    task = asyncio.create_task(collect(provider(fake), endless()))
    await asyncio.sleep(0.5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await asyncio.to_thread(fake.closed.wait, 3)


async def test_batch_transcribe_uses_the_same_path(fake: Fake) -> None:
    async def after_flush(ws: ServerConnection) -> None:
        await ws.send(data("batch"))

    fake.on_flush = after_flush
    out = await provider(fake).transcribe(SECOND * 2, StreamOptions())
    assert [s.text for s in out] == ["batch"]
    assert len([m for m in fake.messages if "audio" in m]) == 10  # 200 ms chunks


async def test_unsupported_operations_say_so_and_the_key_is_not_in_the_repr(fake: Fake) -> None:
    p = provider(fake)
    for call in (
        p.detect_language(b""),
        p.identify_speakers(b"", StreamOptions()),
        p.translate("a", "hi-IN", "en-IN"),
    ):
        with pytest.raises(CapabilityNotSupported):
            await call
    assert KEY not in repr(p) and KEY not in str(p)
    with pytest.raises(ValueError):
        SarvamSpeechProvider("")
    with pytest.raises(ValueError):
        SarvamSpeechProvider(KEY, mode="translate")


# ---- through the real gateway ------------------------------------------------------------------


def test_audio_flows_through_the_gateway_to_a_stored_transcript(
    fake: Fake, client: Any, org_a: dict[str, str]
) -> None:
    from app.speech.registry import register, unregister
    from tests.clinical_helpers import Visit
    from tests.speech_helpers import recording_ready, start_session, stream, token_of, transcript
    from tests.test_gateway import authed, closes_with, connect

    v: Visit = recording_ready(client, org_a)

    async def after_flush(ws: ServerConnection) -> None:
        await ws.send(data("Naku rendu rojula nunchi jwaram undi", lang="te-IN", dur=3.0))

    fake.on_flush = after_flush
    register("sarvam", lambda: SarvamSpeechProvider(KEY, url=fake.url, drain_seconds=0.4))
    client.app.state.settings.speech_provider = "sarvam"  # type: ignore[attr-defined]
    try:
        session = start_session(client, v, language_hint="te-IN")
        iid = session["interaction"]["id"]
        with connect(client, session, None) as ws:
            authed(ws, token_of(v.doctor))
            stream(ws, 3)
            ws.send_json({"type": "stop"})
            assert closes_with(ws) == 1000
        t = transcript(client, v.doctor, iid)
    finally:
        unregister("sarvam")
    assert t["is_development"] is False and t["status"] == "ENDED"
    (seg,) = t["segments"]
    assert seg["raw_text"] == "Naku rendu rojula nunchi jwaram undi"
    assert seg["provider"] == "sarvam"
    assert seg["language"] == "te-IN" and seg["speaker_id"] is None
    assert seg["speaker_role"] == "UNKNOWN" and seg["confidence"] is None
    assert fake.requests[0]["query"]["language-code"] == "te-IN"
