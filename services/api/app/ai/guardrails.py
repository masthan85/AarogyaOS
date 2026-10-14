"""Deterministic checks applied to EVERY model output, whichever model produced it.

The model proposes; this code decides what survives. Nothing here calls a model.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.ai.lexicon import HEDGES, NEGATIONS, contains_cue
from app.ai.schemas import ALLOWED_ATTRIBUTES, KINDS_BY_PURPOSE, RawCandidate

QUESTION_MARKS = ("?", "؟", "？")
# Kinds where a speaker's own account of their body is the content; used for the
# "a clinician said it" flag below.
_PATIENT_EXPERIENCE = {
    "SYMPTOM",
    "ALLERGY",
    "MEDICAL_HISTORY",
    "SURGICAL_HISTORY",
    "CHIEF_COMPLAINT",
}
_CLINICIAN_ROLES = {"DOCTOR", "OTHER_STAFF"}


@dataclass(frozen=True)
class SegmentView:
    """What the guardrails know about a transcript segment (no ids beyond seq)."""

    seq: int
    raw_text: str
    speaker_role: str
    segment_id: str = ""


@dataclass
class Vetted:
    candidate: RawCandidate
    flags: list[str] = field(default_factory=list)
    evidence: list[dict[str, object]] = field(default_factory=list)


@dataclass
class VetResult:
    kept: list[Vetted] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)

    def drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1


def _flat(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def dedupe_key(kind: str, text: str, assertion: str) -> str:
    return f"{kind}|{_flat(re.sub(r'[^\w\s]', ' ', text))}|{assertion}"


def vet_candidates(
    raw: list[dict[str, object]],
    segments: list[SegmentView],
    purpose: str,
    existing_keys: set[str] | None = None,
) -> VetResult:
    """Validate, ground, and de-risk candidates. Order matters and is covered by tests."""
    out = VetResult()
    by_seq = {s.seq: s for s in segments}
    seen = set(existing_keys or ())
    allowed_kinds = KINDS_BY_PURPOSE.get(purpose, frozenset())

    for item in raw:
        try:
            cand = RawCandidate.model_validate(item)
        except ValidationError:
            out.drop("invalid_schema")
            continue

        if cand.kind not in allowed_kinds:
            out.drop("not_allowed_for_purpose")
            continue

        evidence: list[dict[str, object]] = []
        roles: list[str] = []
        grounded = True
        for ev in cand.evidence:
            seg = by_seq.get(ev.seq)
            if seg is None or _flat(ev.quote) not in _flat(seg.raw_text):
                grounded = False  # the model quoted something the transcript does not contain
                break
            evidence.append(
                {
                    "segment_id": seg.segment_id,
                    "seq": seg.seq,
                    "quote": ev.quote,
                    "speaker_role": seg.speaker_role,
                }
            )
            roles.append(seg.speaker_role)
        if not grounded:
            out.drop("unsupported_evidence")
            continue

        if any(any(q in ev.quote for q in QUESTION_MARKS) for ev in cand.evidence):
            out.drop("from_question")  # a question is not a statement of fact
            continue

        flags: list[str] = []
        assertion = cand.assertion
        quotes = " ".join(ev.quote for ev in cand.evidence)
        if assertion == "PRESENT" and contains_cue(quotes, HEDGES):
            assertion = "POSSIBLE"  # downgrade only; hedging is never promoted to certainty
            flags.append("hedged_downgraded")
        if assertion == "PRESENT" and contains_cue(quotes, NEGATIONS):
            flags.append("negation_cue_check")
        if "UNKNOWN" in roles:
            flags.append("speaker_unassigned")
        if (
            cand.kind in _PATIENT_EXPERIENCE
            and cand.subject == "PATIENT"
            and roles
            and all(r in _CLINICIAN_ROLES for r in roles)
        ):
            flags.append("stated_by_clinician")

        allowed = ALLOWED_ATTRIBUTES.get(cand.kind, frozenset())
        attrs = {k: v for k, v in cand.attributes.items() if k in allowed}
        if len(attrs) != len(cand.attributes):
            flags.append("unknown_attributes_removed")

        key = dedupe_key(cand.kind, cand.text, assertion)
        if key in seen:
            out.drop("duplicate")
            continue
        seen.add(key)

        out.kept.append(
            Vetted(
                cand.model_copy(update={"assertion": assertion, "attributes": attrs}),
                flags,
                evidence,
            )
        )
    return out


# Phrases that claim an action the software has no authority to take.
_AUTONOMOUS = re.compile(
    r"\b(i|we|the system|ai)\s+(have|has|had|will|did|am going to)?\s*"
    r"(prescribed|ordered|started|stopped|changed|cancelled|diagnosed|referred|discharged)\b"
    r"|\b(has been|have been)\s+"
    r"(prescribed|ordered|started|stopped|cancelled|diagnosed|referred|discharged)\b",
    re.IGNORECASE,
)


def claims_autonomous_action(text: str) -> bool:
    return bool(_AUTONOMOUS.search(text))
