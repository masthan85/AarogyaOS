"""Tests for the database-free speech package."""

import asyncio
import base64
from collections.abc import AsyncIterator

import pytest

from app.core.crypto import FieldCrypto
from app.speech import eval as sev
from app.speech.audio_store import LocalEncryptedAudioStore
from app.speech.dev_provider import DevelopmentSpeechProvider
from app.speech.pipeline import StreamFailed, run_stream
from app.speech.provider import (
    BYTES_PER_SECOND,
    CapabilityNotSupported,
    ProviderError,
    ProviderNotAvailable,
    RecognisedSegment,
    SpeechProvider,
    StreamOptions,
)
from app.speech.registry import PENDING, get_provider, register
from app.speech.synthetic import SCRIPTS

SECOND = b"\x00\x00" * (BYTES_PER_SECOND // 2)


async def frames(seconds: int) -> AsyncIterator[bytes]:
    for _ in range(seconds):
        yield SECOND


async def collect(
    provider: SpeechProvider, seconds: int, lang: str = "en-IN"
) -> list[RecognisedSegment]:
    return [
        s
        async for s in provider.stream_transcribe(
            frames(seconds), StreamOptions(language_hint=lang)
        )
    ]


def test_dev_provider_emits_partial_before_final_in_order_as_audio_arrives() -> None:
    segs = asyncio.run(collect(DevelopmentSpeechProvider(), 12))
    finals = [s for s in segs if s.is_final]
    assert len(finals) == 4  # the whole English script
    assert [s.speaker_id for s in finals] == ["spk_0", "spk_1", "spk_0", "spk_1"]
    first_partial = next(i for i, s in enumerate(segs) if not s.is_final)
    first_final = next(i for i, s in enumerate(segs) if s.is_final)
    assert first_partial < first_final
    assert all(s.confidence is None for s in segs if not s.is_final)  # a guess carries no score
    assert finals[0].start_ms == 0 and finals[1].start_ms == finals[0].end_ms


def test_dev_provider_says_nothing_without_audio_and_never_runs_ahead() -> None:
    assert asyncio.run(collect(DevelopmentSpeechProvider(), 0)) == []
    assert len([s for s in asyncio.run(collect(DevelopmentSpeechProvider(), 3)) if s.is_final]) == 1


def test_code_switching_metadata_matches_the_text() -> None:
    segs = asyncio.run(collect(DevelopmentSpeechProvider(), 6, "te-IN"))
    mixed = next(s for s in segs if s.is_final and s.secondary_language)
    assert mixed.language == "te-IN" and mixed.secondary_language == "en-IN"
    assert "nunchi fever undi" in mixed.text  # the spec's Telugu + English example, verbatim
    assert [mixed.text[s.start_char : s.end_char] for s in mixed.code_switch_spans] == [
        "two days",
        "night time",
        "little breathing problem",
    ]


def test_every_synthetic_span_points_inside_its_text() -> None:
    assert {"en-IN", "hi-IN", "te-IN", "ta-IN"} <= set(SCRIPTS)
    for lines in SCRIPTS.values():
        assert len({line.speaker for line in lines}) >= 2
        for line in lines:
            for span in line.spans:
                assert 0 <= span.start_char < span.end_char <= len(line.text)


def test_dev_provider_is_honest_about_what_it_cannot_do() -> None:
    p = DevelopmentSpeechProvider()
    assert p.is_development and p.capabilities.diarisation == "stream"
    assert not p.capabilities.translation
    with pytest.raises(CapabilityNotSupported):
        asyncio.run(p.translate("hello", "en-IN", "hi-IN"))
    batch = asyncio.run(p.transcribe(SECOND * 7, StreamOptions()))
    assert len(batch) == 2


def test_registry_refuses_unbuilt_unknown_and_production_dev_providers() -> None:
    with pytest.raises(ProviderNotAvailable, match="could not be read"):
        get_provider("sarvam", environment="production")
    assert "sarvam" in PENDING
    with pytest.raises(ProviderNotAvailable, match="Unknown"):
        get_provider("nonsense", environment="development")
    with pytest.raises(ProviderNotAvailable, match="No speech provider"):
        get_provider("  ", environment="development")
    with pytest.raises(ProviderNotAvailable, match="disabled in production"):
        get_provider("development", environment="production")
    assert get_provider("Development", environment="test").name == "development"


class FailingProvider(DevelopmentSpeechProvider):
    name, model = "failing", "x"

    def __init__(self, after_frames: int = 0) -> None:
        super().__init__()
        self._after = after_frames

    async def stream_transcribe(  # type: ignore[override]
        self, audio: AsyncIterator[bytes], opts: StreamOptions
    ) -> AsyncIterator[RecognisedSegment]:
        n = 0
        async for _ in audio:
            n += 1
            if n > self._after:
                raise ProviderError("boom with secret patient text")
        return
        yield  # pragma: no cover  (makes this an async generator)


def drive(primary: SpeechProvider, fallback: SpeechProvider | None, seconds: int = 8):  # type: ignore[no-untyped-def]
    finals: list[tuple[RecognisedSegment, str]] = []

    async def on_partial(_: RecognisedSegment) -> None: ...

    async def on_final(seg: RecognisedSegment, provider: SpeechProvider) -> None:
        finals.append((seg, provider.name))

    stats = asyncio.run(
        run_stream(primary, fallback, frames(seconds), StreamOptions(), on_partial, on_final)
    )
    return stats, finals


def test_pipeline_counts_audio_segments_and_latency() -> None:
    stats, finals = drive(DevelopmentSpeechProvider(), None, 6)
    assert stats.audio_seconds == 6 and stats.segments == len(finals) == 2
    assert stats.first_segment_latency_ms is not None and stats.errors == 0


def test_pipeline_falls_back_and_records_the_gap() -> None:
    register("failing", lambda: FailingProvider(after_frames=1))
    stats, finals = drive(FailingProvider(after_frames=1), DevelopmentSpeechProvider(), 8)
    assert (
        stats.fell_back_from == "failing" and stats.provider == "development" and stats.errors == 1
    )
    assert finals and {p for _, p in finals} == {"development"}
    assert any("not transcribed" in n for n in stats.notes)


def test_pipeline_reports_total_failure_with_stats_and_without_leaking_text() -> None:
    with pytest.raises(StreamFailed) as exc:
        drive(FailingProvider(), None, 3)
    assert exc.value.stats.errors == 1 and exc.value.stats.audio_bytes > 0
    assert "secret patient text" not in str(exc.value)  # the message names the type only
    with pytest.raises(StreamFailed) as both:
        drive(FailingProvider(), FailingProvider(), 3)
    assert both.value.stats.errors == 2


def test_word_error_rate() -> None:
    assert sev.word_error_rate("the cat sat", "the cat sat") == 0
    assert sev.word_error_rate("the cat sat", "the dog sat") == pytest.approx(1 / 3)
    assert sev.word_error_rate("a b c d", "a c") == 0.5
    assert sev.word_error_rate("", "") == 0 and sev.word_error_rate("", "x") == 1
    assert sev.word_error_rate("Fever, COUGH!", "fever cough") == 0  # case and punctuation ignored
    assert sev.word_error_rate("naku fever undi", "naku fiver undi") == pytest.approx(1 / 3)


def test_character_error_rate_handles_indic_scripts() -> None:
    assert sev.character_error_rate("बुखार", "बुखार") == 0
    assert 0 < sev.character_error_rate("बुखार", "बुखर") < 1


def test_medical_term_error_rate_counts_missed_terms_only() -> None:
    lex = {"fever", "cough", "penicillin"}
    ref = "patient has fever and cough allergic to penicillin"
    assert sev.medical_term_error_rate(ref, ref, lex) == 0
    assert sev.medical_term_error_rate(
        ref, "patient has fever and cough allergic to penicilin", lex
    ) == pytest.approx(1 / 3)
    assert sev.medical_term_error_rate("no terms here", "anything", lex) == 0


def test_language_id_and_speaker_attribution_scores() -> None:
    assert sev.language_id_accuracy(["te", "hi", "en"], ["te", "hi", "hi"]) == pytest.approx(2 / 3)
    # Provider labels are arbitrary: swapped names are still perfect attribution.
    assert sev.speaker_attribution_accuracy(["doc", "pat", "doc"], ["B", "A", "B"]) == 1.0
    assert (
        sev.speaker_attribution_accuracy(["doc", "pat", "doc", "pat"], ["A", "A", "A", "B"]) == 0.75
    )
    with pytest.raises(ValueError):
        sev.language_id_accuracy(["a"], [])


def test_encrypted_audio_store_roundtrip_and_safety(tmp_path) -> None:  # type: ignore[no-untyped-def]
    crypto = FieldCrypto(base64.b64encode(b"k" * 32).decode())
    store = LocalEncryptedAudioStore(str(tmp_path), crypto)
    secret = b"SECRET-PCM-AUDIO-BYTES" * 10
    w = store.writer("org/ia.audio")
    w.append(secret)
    w.append(b"second")
    assert w.close() == len(secret) + 6
    assert b"SECRET" not in (tmp_path / "org" / "ia.audio").read_bytes()
    assert list(store.read_chunks("org/ia.audio")) == [secret, b"second"]
    assert (
        store.exists("org/ia.audio")
        and store.delete("org/ia.audio")
        and not store.exists("org/ia.audio")
    )
    assert store.delete("org/ia.audio") is False
    with pytest.raises(ValueError):
        store.writer("../../etc/passwd")
    with pytest.raises(Exception):  # noqa: B017, PT011
        other = LocalEncryptedAudioStore(
            str(tmp_path), FieldCrypto(base64.b64encode(b"z" * 32).decode())
        )
        w2 = store.writer("a/b.audio")
        w2.append(b"x")
        w2.close()
        list(other.read_chunks("a/b.audio"))
