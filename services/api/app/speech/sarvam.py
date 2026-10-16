"""Sarvam AI streaming speech-to-text adapter.

Written against the wire protocol in Sarvam's official Python SDK (`sarvamai` 0.1.37, the
`speech_to_text_streaming` client: generally-available `/speech-to-text/ws` endpoint, not the beta
realtime one). That is the source for everything below; the vendor's web documentation could not
be read from the build environment. **It has not been run against the live service** (no
credentials here): run `scripts/sarvam_live_check.py` with a key before relying on it. What the
protocol gives us and what it does not:

* Auth: `Api-Subscription-Key` header. URL: `wss://api.sarvam.ai/speech-to-text/ws` + query.
* Audio: JSON `{"audio": {"data": <base64>, "sample_rate": 16000, "encoding": "audio/wav"}}`; raw
  PCM16 is declared through the `input_audio_codec=pcm_s16le` query parameter.
* `{"type": "flush"}` (needs `flush_signal=true`) forces the final transcript of buffered audio.
  There is no end-of-stream message: after flushing we wait briefly for stragglers, then close.
* Replies: `{"type": "data", "data": {transcript, language_code, language_probability,
  metrics}}`, `{"type": "events", ...}` (VAD START_SPEECH / END_SPEECH), `{"type": "error", ...}`.
* Over the WebSocket there are **no timestamps, no diarisation and no confidence score**, and
  results are final utterances found by the vendor's voice-activity detection (no live partials
  on this endpoint). So segment times here are *estimates* (when speech started in the audio we
  sent, plus the vendor's reported audio duration), speaker labels are absent (people assign
  roles), and `confidence` is None rather than invented.

Error messages from the vendor are never propagated (only their short code): they could echo
content, and the API key must never reach a log.
"""

import asyncio
import base64
import contextlib
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any
from urllib.parse import urlencode

from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus, WebSocketException

from app.speech.provider import (
    BYTES_PER_SECOND,
    CapabilityNotSupported,
    LanguageGuess,
    ProviderError,
    RecognisedSegment,
    SpeakerTurn,
    SpeechCapabilities,
    StreamOptions,
    Translation,
)

NAME = "sarvam"
DEFAULT_URL = "wss://api.sarvam.ai/speech-to-text/ws"
LANGUAGES = frozenset(
    "en-IN hi-IN bn-IN gu-IN kn-IN ml-IN mr-IN od-IN pa-IN ta-IN te-IN as-IN ur-IN ne-IN "
    "kok-IN ks-IN sd-IN sa-IN sat-IN mni-IN brx-IN mai-IN doi-IN".split()
)
MODES = frozenset({"transcribe", "verbatim", "translit", "codemix"})  # "translate" changes meaning
DRAIN_SECONDS = 3.0  # how long to wait for the last transcripts after the audio has ended


class SarvamSpeechProvider:
    name = NAME
    is_development = False
    capabilities = SpeechCapabilities(
        streaming=True,
        diarisation="none",
        word_timestamps=False,
        code_mixed=True,
        translation=False,
        languages=LANGUAGES,
    )

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "saaras:v4",
        mode: str = "transcribe",
        url: str = DEFAULT_URL,
        drain_seconds: float = DRAIN_SECONDS,
        on_message: Callable[[dict[str, Any]], None] | None = None,
        use_language_hint: bool = True,
    ) -> None:
        if not api_key:
            raise ValueError("A Sarvam API key is required")
        if mode not in MODES:
            raise ValueError(f"Unsupported Sarvam mode: {mode}")
        self._key = api_key
        self.model = model
        self._mode = mode
        self._url = url
        self._drain = drain_seconds
        # Off in the app: consultations mix languages and a fixed one mis-writes the other.
        self._use_hint = use_language_hint
        # Diagnostics for the live-check script only: sees every vendor reply. Not used by the app.
        self._on_message = on_message

    def __repr__(self) -> str:  # never show the key
        return f"SarvamSpeechProvider(model={self.model!r}, mode={self._mode!r})"

    def _endpoint(self, opts: StreamOptions) -> str:
        hint = opts.language_hint
        language = (
            hint if self._use_hint and hint in LANGUAGES else "unknown"
        )  # unknown => vendor auto-detects
        query = {
            "language-code": language,
            "model": self.model,
            "mode": self._mode,
            "sample_rate": str(opts.sample_rate),
            "input_audio_codec": "pcm_s16le",
            "vad_signals": "true",
            "flush_signal": "true",
        }
        return f"{self._url}?{urlencode(query)}"

    async def stream_transcribe(
        self, audio: AsyncIterator[bytes], opts: StreamOptions
    ) -> AsyncIterator[RecognisedSegment]:
        try:
            ws = await connect(
                self._endpoint(opts),
                additional_headers={"Api-Subscription-Key": self._key},
                max_size=2**20,
                open_timeout=10,
            )
        except InvalidStatus as exc:
            raise ProviderError(
                f"sarvam refused the connection ({exc.response.status_code})"
            ) from None
        except (OSError, TimeoutError, WebSocketException):
            raise ProviderError("sarvam connection failed") from None

        sent_ms = 0  # audio we have sent so far, in ms of audio (not wall-clock)
        sending_done = asyncio.Event()
        done_at = [0.0]  # monotonic time the audio ended (the drain window starts there)
        out: asyncio.Queue[RecognisedSegment | Exception | None] = asyncio.Queue()

        async def sender() -> None:
            nonlocal sent_ms
            try:
                async for frame in audio:
                    payload = {
                        "audio": {
                            "data": base64.b64encode(frame).decode("ascii"),
                            "sample_rate": opts.sample_rate,
                            "encoding": "audio/wav",
                        }
                    }
                    await ws.send(json.dumps(payload))
                    sent_ms += int(len(frame) / BYTES_PER_SECOND * 1000)
                await ws.send(json.dumps({"type": "flush"}))
            except WebSocketException:
                pass  # the receiver reports the failure
            finally:
                done_at[0] = time.monotonic()
                sending_done.set()

        async def receiver() -> None:
            speech_started_ms: int | None = None
            last_end_ms = 0
            try:
                idle_since = time.monotonic()
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), 0.2)
                    except TimeoutError:
                        quiet_since = max(idle_since, done_at[0])
                        if sending_done.is_set() and time.monotonic() - quiet_since >= self._drain:
                            return  # the audio has ended and nothing more is arriving
                        continue
                    idle_since = time.monotonic()
                    msg = _parse(raw)
                    if self._on_message is not None:
                        self._on_message(msg)
                    kind, data = msg.get("type"), msg.get("data") or {}
                    if kind == "events":
                        if data.get("signal_type") == "START_SPEECH":
                            speech_started_ms = sent_ms
                    elif kind == "error":
                        code = str(data.get("code", "unknown"))[:60]
                        raise ProviderError(f"sarvam error: {code}")
                    elif kind == "data":
                        text = str(data.get("transcript", "")).strip()
                        duration_ms = int(
                            float((data.get("metrics") or {}).get("audio_duration") or 0) * 1000
                        )
                        start = last_end_ms if speech_started_ms is None else speech_started_ms
                        start = max(start, last_end_ms)
                        end = max(start + duration_ms, start)
                        last_end_ms, speech_started_ms = end, None
                        if text:
                            await out.put(
                                RecognisedSegment(
                                    text=text,
                                    start_ms=start,
                                    end_ms=end,
                                    is_final=True,
                                    language=data.get("language_code"),
                                    language_confidence=data.get("language_probability"),
                                    confidence=None,
                                )
                            )
            except WebSocketException:
                if not sending_done.is_set():
                    raise ProviderError("sarvam connection lost") from None

        async def guarded() -> None:
            try:
                await receiver()
            except Exception as exc:  # delivered to the consumer, not lost in a task
                await out.put(exc)
            else:
                await out.put(None)  # end of stream, only after any error has been queued

        tasks = [asyncio.create_task(sender()), asyncio.create_task(guarded())]
        try:
            while True:
                item = await out.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    if isinstance(item, ProviderError):
                        raise item
                    raise ProviderError("sarvam stream failed") from None
                yield item
        finally:
            for t in tasks:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t
            with contextlib.suppress(Exception):
                await ws.close()

    async def transcribe(self, audio: bytes, opts: StreamOptions) -> list[RecognisedSegment]:
        async def chunks() -> AsyncIterator[bytes]:
            step = BYTES_PER_SECOND // 5  # 200 ms
            for i in range(0, len(audio), step):
                yield audio[i : i + step]

        return [s async for s in self.stream_transcribe(chunks(), opts)]

    async def detect_language(self, audio: bytes) -> LanguageGuess:
        raise CapabilityNotSupported("Sarvam streaming does not offer separate language detection")

    async def identify_speakers(self, audio: bytes, opts: StreamOptions) -> list[SpeakerTurn]:
        raise CapabilityNotSupported("Sarvam streaming does not provide diarisation")

    async def translate(self, text: str, source: str, target: str) -> Translation:
        raise CapabilityNotSupported("Sarvam translation is not wired in this adapter")


def _parse(raw: str | bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


__all__ = ["DEFAULT_URL", "NAME", "SarvamSpeechProvider"]
