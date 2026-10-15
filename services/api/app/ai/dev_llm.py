"""Development "LLM": a tiny lexicon-based extractor. It is NOT a model.

Purpose: drive the extraction/review pipeline end to end on the synthetic development transcripts
without credentials. It understands only the starter lexicon (a handful of symptoms, durations,
and the phrase "allergic to X"), it is deliberately naive (it will quote questions and ignore
hedging so that the deterministic guardrails have real work to do), and every result is labelled
as development. Refused in production. It cannot reason, so it produces no clinical suggestions
beyond echoing a retrieved reference passage.
"""

import json
import re
import time
from typing import Any

from app.ai.lexicon import NEGATIONS, SYMPTOMS, contains_cue, norm
from app.ai.llm import LLMRequest, LLMResponse

NAME = "development"
_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "ek": 1,
    "do": 2,
    "teen": 3,
    "char": 4,
    "paanch": 5,
}
_DURATION = re.compile(
    r"(\d+|one|two|three|four|five|six|seven|ek|do|teen|char|paanch)\s*(?:days?|din|rojula|nal)\b",
    re.IGNORECASE,
)
_ALLERGY = re.compile(
    r"allergic to ([a-z][a-z\- ]*?)(?: as a child| when |[.,;?!]|$)", re.IGNORECASE
)
_SENTENCE = re.compile(r"[^.?!।]+[.?!।]?")


def _sentences(text: str) -> list[str]:
    return [m.group(0).strip() for m in _SENTENCE.finditer(text) if m.group(0).strip()]


def _find(sentence: str) -> list[tuple[str, str]]:
    low = norm(sentence)
    found: dict[str, str] = {}
    for _lang, surface, canonical in SYMPTOMS:
        s = norm(surface)
        hit = re.search(rf"(?<!\w){re.escape(s)}(?!\w)", low) if s.isascii() else s in low
        if hit and canonical not in found:
            found[canonical] = surface
    if "chest" in low and ("pain" in low or "dard" in low) and "chest pain" not in found:
        found["chest pain"] = "chest"
    return list(found.items())


class DevelopmentLLMProvider:
    name = NAME
    model = "lexicon-extractor-v1"
    is_development = True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        started = time.monotonic()
        if request.task == "clinical_extraction":
            body = self._extract(request.payload)
        elif request.task == "suggestions":
            body = self._suggest(request.payload)
        elif request.task == "chart_qa":
            body = self._chart_qa(request.payload)
        else:
            body = {}
        text = json.dumps(body, ensure_ascii=False)
        return LLMResponse(
            text=text,
            input_tokens=len(request.prompt) // 4,
            output_tokens=len(text) // 4,
            latency_ms=int((time.monotonic() - started) * 1000),
            token_counts_are_estimates=True,
        )

    @staticmethod
    def _extract(payload: dict[str, Any]) -> dict[str, Any]:
        allowed = set(payload["allowed_kinds"])
        out: list[dict[str, Any]] = []
        for seg in payload["segments"]:
            if seg.get("context_only"):
                continue
            for sentence in _sentences(seg["text"]):
                evidence = [{"seq": seg["seq"], "quote": sentence}]
                duration = _DURATION.search(sentence)
                days = None
                if duration:
                    raw = duration.group(1).lower()
                    days = int(raw) if raw.isdigit() else _NUMBERS[raw]
                negated = contains_cue(sentence, NEGATIONS)
                mild = bool(re.search(r"\b(little|mild|thoda)\b", sentence, re.IGNORECASE))
                if "SYMPTOM" in allowed:
                    for canonical, surface in _find(sentence):
                        attrs: dict[str, str] = {}
                        if days and not negated:
                            attrs["duration"] = f"{days} days"
                        if mild:
                            attrs["severity"] = "mild"
                        out.append(
                            {
                                "kind": "SYMPTOM",
                                "text": canonical,
                                "assertion": "ABSENT" if negated else "PRESENT",
                                "subject": "PATIENT",
                                "attributes": attrs,
                                "original_term": surface,
                                "evidence": evidence,
                            }
                        )
                    low = norm(sentence)
                    if any(w in low for w in ("night", "raat")) and any(
                        w in low for w in ("ekkuva", "romba", "zyada", "more", "worse", "adhigama")
                    ):
                        out.append(
                            {
                                "kind": "SYMPTOM",
                                "text": "symptoms worse at night",
                                "assertion": "PRESENT",
                                "subject": "PATIENT",
                                "attributes": {"pattern": "worse at night"},
                                "original_term": None,
                                "evidence": evidence,
                            }
                        )
                if "ALLERGY" in allowed and (m := _ALLERGY.search(sentence)):
                    substance = m.group(1).strip()
                    attrs = {"substance": substance}
                    if re.search(r"as a child|when i was young", sentence, re.IGNORECASE):
                        attrs["when"] = "childhood"
                    out.append(
                        {
                            "kind": "ALLERGY",
                            "text": f"allergy to {substance}",
                            "assertion": "PRESENT",
                            "subject": "PATIENT",
                            "attributes": attrs,
                            "original_term": None,
                            "evidence": evidence,
                        }
                    )
        return {"candidates": out}

    @staticmethod
    def _chart_qa(payload: dict[str, Any]) -> dict[str, Any]:
        """Naive on purpose: returns the two entries sharing the most words with the question."""
        words = set(re.findall(r"[a-z0-9]{3,}", payload["question"].casefold()))
        scored = []
        for item in payload["items"]:
            overlap = len(words & set(re.findall(r"[a-z0-9]{3,}", item["text"].casefold())))
            if overlap:
                scored.append((overlap, item))
        scored.sort(key=lambda t: -t[0])
        return {"statements": [{"text": i["text"], "refs": [i["ref"]]} for _, i in scored[:2]]}

    @staticmethod
    def _suggest(payload: dict[str, Any]) -> dict[str, Any]:
        hits = payload.get("knowledge") or []
        if not hits or "GUIDELINE" not in payload["allowed_categories"]:
            return {"suggestions": []}
        top = hits[0]
        return {
            "suggestions": [
                {
                    "category": "GUIDELINE",
                    "title": f"Reference available: {top['title']}"[:160],
                    "explanation": top["text"][:700],
                    "uncertainty": "MEDIUM",
                    "uncertainty_note": "Found by similarity; check it applies.",
                    "supporting_refs": [],
                    "source_chunk_ids": [top["chunk_id"]],
                }
            ]
        }
