"""Offline evaluation of clinical extraction against hand-labelled synthetic transcripts.

    python -m app.ai.eval [evals/extraction_gold.json]

It runs the configured provider's output through the same guardrails the product uses and scores
what survives. It reports error rates alongside precision/recall because a model that is "accepted
a lot" can still be unsafe: acceptance by clinicians is not a target to optimise on its own.

Limits: the bundled fixtures are tiny and synthetic, so the numbers only show that the harness
works. Meaningful numbers need transcripts labelled by clinicians, in the languages you serve.
Suggestion quality (unsafe / unsupported rates) needs clinician-labelled cases and is not scored
here; at runtime every dropped suggestion is counted instead.
"""

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.ai import guardrails
from app.ai.dev_llm import DevelopmentLLMProvider
from app.ai.llm import LLMProvider, LLMRequest
from app.ai.prompts import EXTRACTION_VERSION, render_extraction
from app.ai.schemas import KINDS_BY_PURPOSE

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "evals" / "extraction_gold.json"


def _norm(s: str) -> str:
    return " ".join(s.casefold().split())


def run_case(llm: LLMProvider, case: dict[str, Any]) -> list[dict[str, str]]:
    segs = case["segments"]
    payload = {
        "allowed_kinds": sorted(KINDS_BY_PURPOSE[case["purpose"]]),
        "segments": [
            {"seq": s["seq"], "speaker_role": s["role"], "language": None, "text": s["text"]}
            for s in segs
        ],
    }
    system, prompt = render_extraction(payload)
    resp = asyncio.run(
        llm.complete(LLMRequest("clinical_extraction", EXTRACTION_VERSION, system, prompt, payload))
    )
    raw = json.loads(resp.text)["candidates"]
    views = [guardrails.SegmentView(s["seq"], s["text"], s["role"], str(s["seq"])) for s in segs]
    vetted = guardrails.vet_candidates(raw, views, case["purpose"])
    return [
        {"kind": v.candidate.kind, "text": v.candidate.text, "assertion": v.candidate.assertion}
        for v in vetted.kept
    ]


def score(cases: list[dict[str, Any]], llm: LLMProvider) -> dict[str, Any]:
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)
    neg_total = neg_right = 0
    for case in cases:
        got = {(g["kind"], _norm(g["text"]), g["assertion"]) for g in run_case(llm, case)}
        gold = {(g["kind"], _norm(g["text"]), g["assertion"]) for g in case["gold"]}
        for k, _t, _a in got & gold:
            tp[k] += 1
        for k, _t, _a in got - gold:
            fp[k] += 1
        for k, _t, _a in gold - got:
            fn[k] += 1
        for kind, text, assertion in gold:
            if assertion == "ABSENT":
                neg_total += 1
                neg_right += (kind, text, "ABSENT") in got
    kinds = sorted(set(tp) | set(fp) | set(fn))

    def ratio(a: int, b: int) -> float | None:
        return round(a / b, 3) if b else None

    per_kind = {
        k: {
            "precision": ratio(tp[k], tp[k] + fp[k]),
            "recall": ratio(tp[k], tp[k] + fn[k]),
            "tp": tp[k],
            "fp": fp[k],
            "fn": fn[k],
        }
        for k in kinds
    }
    t, f, m = sum(tp.values()), sum(fp.values()), sum(fn.values())
    return {
        "provider": llm.name,
        "model": llm.model,
        "cases": len(cases),
        "per_kind": per_kind,
        "precision": ratio(t, t + f),
        "recall": ratio(t, t + m),
        "unsupported_extra_rate": ratio(f, t + f),  # extracted but not in the gold labels
        "omission_rate": ratio(m, t + m),  # in the gold labels but missed
        "negation_accuracy": ratio(neg_right, neg_total),
    }


def main(argv: list[str]) -> None:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_FILE
    cases = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps(score(cases, DevelopmentLLMProvider()), indent=2))  # noqa: T201


if __name__ == "__main__":
    main(sys.argv)
