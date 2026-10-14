"""Development speech provider: replays a scripted synthetic conversation as audio arrives.

It ignores the audio content entirely and emits one scripted line for every N seconds of audio
received, so the whole pipeline (gateway, storage, polling, speaker assignment, consent
enforcement) can be exercised without credentials. Every segment it produces is labelled with
provider "development" and the UI shows a DEVELOPMENT badge. It is refused in production.
"""

from collections.abc import AsyncIterator

from app.speech.provider import (
    BYTES_PER_SECOND,
    CapabilityNotSupported,
    LanguageGuess,
    RecognisedSegment,
    SpeakerTurn,
    SpeechCapabilities,
    StreamOptions,
    Translation,
)
from app.speech.synthetic import ScriptLine, script_for

NAME = "development"


class DevelopmentSpeechProvider:
    name = NAME
    model = "scripted-synthetic-v1"
    is_development = True
    capabilities = SpeechCapabilities(
        streaming=True,
        diarisation="stream",
        word_timestamps=False,
        code_mixed=True,
        languages=frozenset({"en-IN", "hi-IN", "te-IN", "ta-IN"}),
    )

    def __init__(self, script: list[ScriptLine] | None = None) -> None:
        self._script = script

    def _lines(self, opts: StreamOptions) -> list[ScriptLine]:
        return self._script or script_for(opts.language_hint)

    @staticmethod
    def _segment(line: ScriptLine, start_ms: int, final: bool) -> RecognisedSegment:
        text = line.text if final else line.text[: max(1, len(line.text) // 2)]
        return RecognisedSegment(
            text=text,
            start_ms=start_ms,
            end_ms=start_ms + int(line.seconds * 1000),
            is_final=final,
            speaker_id=line.speaker,
            language=line.language,
            secondary_language=line.secondary,
            language_confidence=0.95,
            confidence=line.confidence if final else None,
            code_switch_spans=line.spans if final else (),
        )

    async def stream_transcribe(
        self, audio: AsyncIterator[bytes], opts: StreamOptions
    ) -> AsyncIterator[RecognisedSegment]:
        lines = self._lines(opts)
        received = 0
        next_index = 0
        elapsed_ms = 0
        async for frame in audio:
            received += len(frame)
            while next_index < len(lines):
                line = lines[next_index]
                needed = int((elapsed_ms / 1000 + line.seconds) * BYTES_PER_SECOND)
                half = int((elapsed_ms / 1000 + line.seconds / 2) * BYTES_PER_SECOND)
                if received >= needed:
                    yield self._segment(line, elapsed_ms, final=True)
                    elapsed_ms += int(line.seconds * 1000)
                    next_index += 1
                elif received >= half:
                    yield self._segment(line, elapsed_ms, final=False)
                    break
                else:
                    break

    async def transcribe(self, audio: bytes, opts: StreamOptions) -> list[RecognisedSegment]:
        out: list[RecognisedSegment] = []
        elapsed = 0
        for line in self._lines(opts):
            if len(audio) < int((elapsed / 1000 + line.seconds) * BYTES_PER_SECOND):
                break
            out.append(self._segment(line, elapsed, final=True))
            elapsed += int(line.seconds * 1000)
        return out

    async def detect_language(self, audio: bytes) -> LanguageGuess:
        return LanguageGuess("en-IN", 0.5)

    async def identify_speakers(self, audio: bytes, opts: StreamOptions) -> list[SpeakerTurn]:
        turns, elapsed = [], 0
        for line in self._lines(opts):
            turns.append(SpeakerTurn(line.speaker, elapsed, elapsed + int(line.seconds * 1000)))
            elapsed += int(line.seconds * 1000)
        return turns

    async def translate(self, text: str, source: str, target: str) -> Translation:
        raise CapabilityNotSupported("The development provider does not translate")
