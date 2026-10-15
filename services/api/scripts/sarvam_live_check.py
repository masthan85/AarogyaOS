"""Check the Sarvam adapter against the REAL service with your own key. Run this before any pilot.

    AAROGYA_SARVAM_API_KEY=... python scripts/sarvam_live_check.py sample.wav [hi-IN]

`sample.wav` must be 16 kHz, mono, 16-bit PCM. Use synthetic or consented audio ONLY: it is sent to
Sarvam's servers. The script streams the file at real-time speed, then prints each final segment
with its estimated times, and exits non-zero on any provider error.

What to look for (the adapter was written from the vendor SDK, not run live):
  1. It connects and does not raise ("refused the connection (401)" = wrong key).
  2. Segments arrive with the text you expect. If raw PCM is rejected or garbled, the vendor may
     want a WAV container on this endpoint despite `input_audio_codec=pcm_s16le`: tell me.
  3. Segments also arrive after the audio ends (the flush works) and nothing is lost at the tail.
  4. Language detection with the "auto" hint, and your languages, mixed Indian-English speech and
     drug names: this is the accuracy that matters. Measure it with `app.speech.eval` against
     reference transcripts before trusting it clinically.
"""

import asyncio
import os
import sys
import wave

sys.path.insert(0, ".")
from app.speech.provider import BYTES_PER_SECOND, SAMPLE_RATE, ProviderError, StreamOptions  # noqa: E402
from app.speech.sarvam import SarvamSpeechProvider  # noqa: E402


async def main(path: str, language: str) -> int:
    key = os.environ.get("AAROGYA_SARVAM_API_KEY", "")
    if not key:
        print("Set AAROGYA_SARVAM_API_KEY")
        return 2
    with wave.open(path, "rb") as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            print("Audio must be 16 kHz mono 16-bit PCM")
            return 2
        pcm = w.readframes(w.getnframes())

    provider = SarvamSpeechProvider(
        key,
        model=os.environ.get("AAROGYA_SARVAM_MODEL", "saaras:v4"),
        mode=os.environ.get("AAROGYA_SARVAM_MODE", "transcribe"),  # type: ignore[arg-type]
    )

    async def chunks():  # type: ignore[no-untyped-def]
        step = BYTES_PER_SECOND // 5
        for i in range(0, len(pcm), step):
            yield pcm[i : i + step]
            await asyncio.sleep(0.2)  # real-time pacing

    print(f"{len(pcm) / BYTES_PER_SECOND:.1f}s of audio, language hint {language}")
    try:
        async for seg in provider.stream_transcribe(
            chunks(), StreamOptions(language_hint=language)
        ):
            span = f"{seg.start_ms / 1000:6.1f}-{seg.end_ms / 1000:6.1f}s ~est"
            print(f"[{span}] ({seg.language}) {seg.text}")
    except ProviderError as exc:
        print(f"PROVIDER ERROR: {exc}")
        return 1
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "auto")))
