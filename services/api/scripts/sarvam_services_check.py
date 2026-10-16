"""Try each Sarvam REST service the app uses, with your own key, and report pass/fail.

    python scripts/sarvam_services_check.py   # SARVAM_API_KEY from the environment or ../../.env

Uses made-up, non-clinical text only. It checks the same code paths the application uses
(app.ai.sarvam), so a pass here means the translation, text-to-speech and chat adapters work
against the real service. Writes `sarvam_check.wav` in the current folder.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, ".")
from app.ai.llm import LLMRequest  # noqa: E402
from app.ai.sarvam import (  # noqa: E402
    SarvamLLMProvider,
    SarvamTranslationProvider,
    SarvamTTSProvider,
    numbers_in,
)

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
KEY = os.environ.get("SARVAM_API_KEY", "")
SAMPLE = "Take one tablet twice a day for 5 days. Come back in 7 days."


async def main() -> int:
    if not KEY:
        print("Set SARVAM_API_KEY (environment or .env at the repository root)")
        return 2
    failures = 0

    async def step(name: str, fn):  # type: ignore[no-untyped-def]
        nonlocal failures
        try:
            print(f"PASS  {name}: {await fn()}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")

    async def translate() -> str:
        out = await SarvamTranslationProvider(KEY).translate(SAMPLE, "en-IN", "hi-IN")
        same = numbers_in(out) == numbers_in(SAMPLE)
        return f"{out!r}  (numbers preserved: {same})"

    async def speak() -> str:
        audio = await SarvamTTSProvider(KEY).synthesize(SAMPLE, "en-IN")
        Path("sarvam_check.wav").write_bytes(audio)
        return f"{len(audio)} bytes written to sarvam_check.wav (play it to listen)"

    async def chat() -> str:
        llm = SarvamLLMProvider(
            KEY, model=os.environ.get("AAROGYA_SARVAM_LLM_MODEL", "sarvam-105b")
        )
        r = await llm.complete(
            LLMRequest("check", "v1", "Reply with one JSON object only.", 'Return {"ok": true}.')
        )
        return f"{r.text.strip()[:80]!r} ({r.input_tokens} in / {r.output_tokens} out tokens)"

    await step("translation en-IN -> hi-IN", translate)
    await step("text-to-speech en-IN", speak)
    await step("chat", chat)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
