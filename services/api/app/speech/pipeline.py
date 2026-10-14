"""Drives one provider (with an optional fallback) over a live audio stream.

Pure asyncio, no database. Persistence is done by the caller through callbacks so this code
can run anywhere. Partial segments are reported for display only and never as final facts.
"""

import time
from collections.abc import AsyncIterator, Awaitable, Callable

from app.speech.provider import (
    ProviderStats,
    RecognisedSegment,
    SpeechProvider,
    StreamOptions,
)

OnPartial = Callable[[RecognisedSegment], Awaitable[None]]
# Final segments also say which provider produced them (it changes if a fallback takes over).
OnFinal = Callable[[RecognisedSegment, SpeechProvider], Awaitable[None]]


class StreamFailed(Exception):
    """Every provider failed. Carries what was measured so cost and errors are never lost."""

    def __init__(self, stats: ProviderStats, cause: Exception) -> None:
        super().__init__(f"{stats.provider} failed: {type(cause).__name__}")
        self.stats = stats
        self.cause = cause


async def run_stream(
    primary: SpeechProvider,
    fallback: SpeechProvider | None,
    audio: AsyncIterator[bytes],
    opts: StreamOptions,
    on_partial: OnPartial,
    on_final: OnFinal,
) -> ProviderStats:
    """Stream audio through `primary`; if it fails, continue with `fallback`.

    Audio consumed by a failed provider is not replayed to the fallback (the stream is live);
    the gap is recorded in the stats so it is visible, not hidden.
    """
    stats = ProviderStats(primary.name, primary.model)
    started = time.monotonic()
    counted = _count(audio, stats)

    async def drive(provider: SpeechProvider) -> None:
        async for seg in provider.stream_transcribe(counted, opts):
            if stats.first_segment_latency_ms is None:
                stats.first_segment_latency_ms = int((time.monotonic() - started) * 1000)
            if seg.is_final:
                stats.segments += 1
                await on_final(seg, provider)
            else:
                await on_partial(seg)

    try:
        await drive(primary)
    except Exception as exc:  # providers must not leak vendor exceptions; treat all as failure
        stats.errors += 1
        stats.notes.append(f"{primary.name} failed: {type(exc).__name__}")
        if fallback is None:
            raise StreamFailed(stats, exc) from exc
        stats.fell_back_from = primary.name
        stats.provider, stats.model = fallback.name, fallback.model
        stats.notes.append("audio during the switch-over was not transcribed")
        try:
            await drive(fallback)
        except Exception as exc2:
            stats.errors += 1
            raise StreamFailed(stats, exc2) from exc2
    return stats


async def _count(audio: AsyncIterator[bytes], stats: ProviderStats) -> AsyncIterator[bytes]:
    async for frame in audio:
        stats.audio_bytes += len(frame)
        yield frame
