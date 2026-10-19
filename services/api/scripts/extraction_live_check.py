"""Try the note-taking assistant on a conversation with a real model, and see what it kept.

    python scripts/extraction_live_check.py sarvam        # needs SARVAM_API_KEY in .env
    python scripts/extraction_live_check.py self_hosted   # needs AAROGYA_SELF_HOSTED_LLM_*
    python scripts/extraction_live_check.py anthropic     # needs AAROGYA_ANTHROPIC_API_KEY
    python scripts/extraction_live_check.py development   # the built-in test extractor, no key
    python scripts/extraction_live_check.py sarvam your.json   # your own conversation, same shape

The default conversation (evals/neurosurgery_sample.json) is invented. Use invented or consented
text ONLY: it is sent to the provider you choose. No database is used. It runs the same prompt and
the same safety checks as the app (exact-quote grounding, hedging, negation, speaker flags), so what
you see is what a doctor would be shown to accept or reject.

What to look for:
* Greetings, work and weather should produce nothing.
* The fall from the scooter should appear as "CIRCUMSTANCE".
* The leg pain and numbness should be symptoms with where and when.
* Amlodipine and the penicillin allergy should be recorded as such.
* The MRI should be a test, and the paracetamol a treatment discussed.
* "Come back after 5 days" should be a follow-up that reads as 5 days.
* The father's slipped disc should be family history, not the patient's.
Anything invented, or taken from a question, is a failure.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, ".")
from app.ai import guardrails  # noqa: E402
from app.ai.followup_when import days_from_phrase  # noqa: E402
from app.ai.llm import LLMProvider, LLMRequest  # noqa: E402
from app.ai.prompts import EXTRACTION_VERSION, render_extraction  # noqa: E402
from app.ai.schemas import KINDS_BY_PURPOSE  # noqa: E402
from app.modules.ai.extraction import parse_json_object  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
DEFAULT = Path(__file__).resolve().parents[1] / "evals" / "neurosurgery_sample.json"


def provider(name: str) -> LLMProvider:
    if name == "sarvam":
        from app.ai.sarvam import SarvamLLMProvider

        return SarvamLLMProvider(
            os.environ["SARVAM_API_KEY"],
            model=os.environ.get("AAROGYA_SARVAM_LLM_MODEL", "sarvam-105b"),
        )
    if name == "self_hosted":
        from app.ai.self_hosted import SelfHostedLLMProvider

        return SelfHostedLLMProvider(
            os.environ["AAROGYA_SELF_HOSTED_LLM_URL"],
            model=os.environ["AAROGYA_SELF_HOSTED_LLM_MODEL"],
            api_key=os.environ.get("AAROGYA_SELF_HOSTED_LLM_API_KEY", ""),
            timeout_seconds=120,
        )
    if name == "anthropic":
        from app.ai.anthropic_llm import AnthropicLLMProvider

        return AnthropicLLMProvider(os.environ["AAROGYA_ANTHROPIC_API_KEY"])
    if name == "development":
        from app.ai.dev_llm import DevelopmentLLMProvider

        return DevelopmentLLMProvider()
    raise SystemExit(f"Unknown provider {name!r}: sarvam, self_hosted, anthropic or development")


async def main(name: str, path: Path) -> int:
    case = json.loads(path.read_text())
    segs = case["segments"]
    payload = {
        "allowed_kinds": sorted(KINDS_BY_PURPOSE[case["purpose"]]),
        "segments": [
            {
                "seq": s["seq"],
                "speaker_role": s["role"],
                "language": None,
                "text": s["text"],
                "context_only": False,
            }
            for s in segs
        ],
    }
    system, prompt = render_extraction(payload)
    llm = provider(name)
    print(f"{llm.name} / {llm.model}, prompt {EXTRACTION_VERSION}, {len(segs)} lines")
    resp = await llm.complete(
        LLMRequest("clinical_extraction", EXTRACTION_VERSION, system, prompt, payload)
    )
    print(f"{resp.input_tokens} tokens in, {resp.output_tokens} out, {resp.latency_ms} ms\n")
    try:
        raw = parse_json_object(resp.text)["candidates"]
    except (ValueError, KeyError, TypeError):
        print(
            "The model did not return the expected JSON, so the app would reject the whole reply:"
        )
        print(resp.text[:1500])
        return 1
    views = [guardrails.SegmentView(s["seq"], s["text"], s["role"], str(s["seq"])) for s in segs]
    vetted = guardrails.vet_candidates(raw, views, case["purpose"])  # type: ignore[arg-type]
    used: set[int] = set()
    print(f"KEPT {len(vetted.kept)} (the doctor would accept or reject each):")
    for v in vetted.kept:
        c = v.candidate
        used.update(e.seq for e in c.evidence)
        extra = ""
        if c.kind == "FOLLOW_UP":
            days = days_from_phrase(c.attributes.get("when") or c.text)
            extra = (
                f"  -> can schedule in {days} days"
                if days
                else "  -> no time readable, plain note only"
            )
        print(f"  [{c.kind}] {c.assertion}: {c.text}  {c.attributes}{extra}")
        for e in c.evidence:
            print(f'      line {e.seq}: "{e.quote}"  flags={v.flags}')
    print(f"\nDROPPED by the safety checks: {dict(vetted.dropped) or 'nothing'}")
    print("\nLines that produced nothing (small talk should be here):")
    for s in segs:
        if s["seq"] not in used:
            print(f"  {s['seq']}: {s['text'][:90]}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    sys.exit(asyncio.run(main(sys.argv[1], Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT)))
