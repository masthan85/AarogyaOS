"""Speech provider abstraction.

Business logic depends on this module only, never on a vendor SDK. A provider declares what it
can do in `SpeechCapabilities`; callers check the declaration and degrade, and a provider that
does not support an operation raises `CapabilityNotSupported`. Nothing is faked.

This package deliberately imports nothing from `app.modules` (no database, no HTTP layer) so it
can be lifted out into a separate service without a rewrite.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

# The only audio format the gateway accepts today: 16 kHz, mono, signed 16-bit little-endian PCM.
SAMPLE_RATE = 16_000
BYTES_PER_SECOND = SAMPLE_RATE * 2


class CapabilityNotSupported(Exception):
    """The provider does not support this operation."""


class ProviderNotAvailable(Exception):
    """The configured provider is unknown, unbuilt, unconfigured or not allowed here."""


class ProviderError(Exception):
    """The provider failed while processing audio."""


@dataclass(frozen=True)
class SpeechCapabilities:
    streaming: bool
    # "stream": speaker labels arrive with live segments; "batch": only after the audio ends.
    diarisation: Literal["none", "batch", "stream"]
    word_timestamps: bool
    code_mixed: bool
    translation: bool = False
    # None = not declared / unrestricted. Language support is data, never a hard-coded list.
    languages: frozenset[str] | None = None


@dataclass(frozen=True)
class CodeSwitchSpan:
    """A run of text inside a segment in a different language (e.g. English inside Telugu)."""

    start_char: int
    end_char: int
    language: str


@dataclass(frozen=True)
class RecognisedSegment:
    text: str  # exactly what the recogniser produced: stored as the raw transcript
    start_ms: int
    end_ms: int
    is_final: bool
    speaker_id: str | None = None  # provider's label, e.g. "spk_0". NOT a role.
    language: str | None = None
    secondary_language: str | None = None
    language_confidence: float | None = None
    confidence: float | None = None  # None when the provider gives no meaningful score
    code_switch_spans: tuple[CodeSwitchSpan, ...] = ()


@dataclass(frozen=True)
class StreamOptions:
    # BCP-47 hint from the patient's profile, or "auto" to let the provider detect.
    language_hint: str = "auto"
    diarise: bool = True
    sample_rate: int = SAMPLE_RATE


@dataclass(frozen=True)
class LanguageGuess:
    language: str
    confidence: float | None = None
    secondary: str | None = None


@dataclass(frozen=True)
class SpeakerTurn:
    speaker_id: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class Translation:
    text: str
    source_language: str
    target_language: str


@runtime_checkable
class SpeechProvider(Protocol):
    name: str
    model: str
    capabilities: SpeechCapabilities
    # True for adapters that produce synthetic output. These are refused in production.
    is_development: bool

    def stream_transcribe(
        self, audio: AsyncIterator[bytes], opts: StreamOptions
    ) -> AsyncIterator[RecognisedSegment]:
        """Consume PCM frames, yield partial and final segments as they become available."""
        ...

    async def transcribe(self, audio: bytes, opts: StreamOptions) -> list[RecognisedSegment]: ...

    async def detect_language(self, audio: bytes) -> LanguageGuess: ...

    async def identify_speakers(self, audio: bytes, opts: StreamOptions) -> list[SpeakerTurn]: ...

    async def translate(self, text: str, source: str, target: str) -> Translation: ...


@dataclass
class ProviderStats:
    """Facts about one streaming run, for cost and quality monitoring. Contains no content."""

    provider: str
    model: str
    audio_bytes: int = 0
    segments: int = 0
    first_segment_latency_ms: int | None = None
    errors: int = 0
    fell_back_from: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def audio_seconds(self) -> float:
        return self.audio_bytes / BYTES_PER_SECOND
