"""The deterministic safety layer, tested without any model or database."""

import asyncio
import json
from typing import Any

import pytest

from app.ai import guardrails as g
from app.ai.dev_llm import DevelopmentLLMProvider
from app.ai.knowledge import (
    HashingEmbeddingProvider,
    NotAvailable,
    NullMedicationKnowledgeProvider,
    NullTerminologyProvider,
    NullTranslationProvider,
    cosine,
)
from app.ai.lexicon import HEDGES, NEGATIONS, contains_cue
from app.ai.llm import LLMRequest, LLMUnavailable
from app.ai.registry import PENDING, get_llm
from app.ai.schemas import ALL_KINDS, KINDS_BY_PURPOSE, RawCandidate

SEGS = [
    g.SegmentView(1, "Any difficulty breathing? Any allergies to medicines?", "DOCTOR", "s1"),
    g.SegmentView(2, "I might have been allergic to penicillin as a child.", "PATIENT", "s2"),
    g.SegmentView(3, "I have had a fever for three days. No cough.", "PATIENT", "s3"),
    g.SegmentView(4, "She says it started last week.", "UNKNOWN", "s4"),
]


def cand(
    kind: str = "SYMPTOM",
    text: str = "fever",
    seq: int = 3,
    quote: str = "I have had a fever",
    **kw: Any,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "text": text,
        "assertion": "PRESENT",
        "subject": "PATIENT",
        "attributes": {},
        "evidence": [{"seq": seq, "quote": quote}],
        **kw,
    }


def vet(
    items: list[dict[str, Any]], purpose: str = "CONSULTATION", existing: set[str] | None = None
) -> g.VetResult:
    return g.vet_candidates(items, SEGS, purpose, existing)


# ---- grounding -------------------------------------------------------------------------


def test_a_grounded_candidate_survives_with_its_evidence_and_speaker() -> None:
    r = vet([cand()])
    assert len(r.kept) == 1 and r.dropped == {}
    ev = r.kept[0].evidence[0]
    assert ev == {
        "segment_id": "s3",
        "seq": 3,
        "quote": "I have had a fever",
        "speaker_role": "PATIENT",
    }


def test_quotes_are_matched_exactly_not_loosely() -> None:
    r = vet([cand(quote="I have had a high fever"), cand(text="x", quote="fever for three days")])
    assert [v.candidate.text for v in r.kept] == ["x"]
    assert r.dropped == {"unsupported_evidence": 1}


def test_matching_ignores_only_case_and_whitespace() -> None:
    assert len(vet([cand(quote="  i HAVE had   a FEVER ")]).kept) == 1


def test_evidence_must_point_at_a_real_segment() -> None:
    assert vet([cand(seq=99)]).dropped == {"unsupported_evidence": 1}


def test_every_quote_of_a_multi_evidence_candidate_must_be_real() -> None:
    c = cand()
    c["evidence"].append({"seq": 2, "quote": "something never said"})
    assert vet([c]).dropped == {"unsupported_evidence": 1}


def test_questions_are_never_facts() -> None:
    r = vet([cand("SYMPTOM", "breathing difficulty", 1, "Any difficulty breathing?")])
    assert r.kept == [] and r.dropped == {"from_question": 1}


# ---- uncertainty ----------------------------------------------------------------------


def test_a_hedged_allergy_is_downgraded_to_possible_and_flagged() -> None:
    c = cand("ALLERGY", "allergy to penicillin", 2, "I might have been allergic to penicillin")
    [v] = vet([c]).kept
    assert v.candidate.assertion == "POSSIBLE" and "hedged_downgraded" in v.flags


@pytest.mark.parametrize("cue", sorted(HEDGES)[:40])
def test_every_hedge_cue_downgrades(cue: str) -> None:
    seg = g.SegmentView(1, f"Allergic to penicillin {cue} sir", "PATIENT")
    [v] = g.vet_candidates(
        [
            cand("ALLERGY", "allergy", 1, "Allergic to penicillin")
            | {"evidence": [{"seq": 1, "quote": f"Allergic to penicillin {cue} sir"}]}
        ],
        [seg],
        "CONSULTATION",
    ).kept
    assert v.candidate.assertion == "POSSIBLE"


def test_hedging_never_upgrades_and_absent_stays_absent() -> None:
    c = cand("SYMPTOM", "cough", 3, "No cough")
    c["assertion"] = "ABSENT"
    [v] = vet([c]).kept
    assert v.candidate.assertion == "ABSENT"


def test_a_present_claim_next_to_a_negation_cue_is_flagged_for_a_human() -> None:
    [v] = vet([cand("SYMPTOM", "cough", 3, "No cough")]).kept
    assert v.candidate.assertion == "PRESENT" and "negation_cue_check" in v.flags


def test_cue_matching_is_by_whole_word() -> None:
    assert not contains_cue("I know it is a nose problem", NEGATIONS)
    assert contains_cue("There is no pain", NEGATIONS)
    assert not contains_cue("hemisphere", frozenset({"emo"}))


# ---- speakers and purpose --------------------------------------------------------------


def test_an_unassigned_speaker_is_flagged_not_trusted() -> None:
    [v] = vet([cand("SYMPTOM", "onset last week", 4, "started last week")]).kept
    assert "speaker_unassigned" in v.flags


def test_a_clinician_stating_the_patients_symptom_is_flagged() -> None:
    seg = g.SegmentView(1, "So you have chest pain.", "DOCTOR")
    [v] = g.vet_candidates(
        [cand("SYMPTOM", "chest pain", 1, "you have chest pain")], [seg], "CONSULTATION"
    ).kept
    assert "stated_by_clinician" in v.flags


def test_reception_recordings_can_only_yield_administrative_kinds() -> None:
    items = [
        cand("SYMPTOM"),
        cand("ALLERGY"),
        cand("MEDICATION"),
        cand("DIAGNOSIS_DISCUSSED"),
        cand("CHIEF_COMPLAINT", "fever for 3 days"),
        cand("FOLLOW_UP", "review next week"),
    ]
    r = vet(items, "RECEPTION")
    assert sorted(v.candidate.kind for v in r.kept) == ["CHIEF_COMPLAINT", "FOLLOW_UP"]
    assert r.dropped == {"not_allowed_for_purpose": 4}
    assert KINDS_BY_PURPOSE["RECEPTION"].isdisjoint(
        {"DIAGNOSIS_DISCUSSED", "ALLERGY", "MEDICATION"}
    )
    assert (
        "DIAGNOSIS_DISCUSSED" not in KINDS_BY_PURPOSE["TRIAGE"]
        and set(ALL_KINDS) == KINDS_BY_PURPOSE["CONSULTATION"]
    )


# ---- schema, duplicates, attributes -----------------------------------------------------


def test_malformed_candidates_are_dropped_individually() -> None:
    bad = [
        {"kind": "NOT_A_KIND", "text": "x", "assertion": "PRESENT", "evidence": []},
        {
            "kind": "SYMPTOM",
            "text": "x",
            "assertion": "CERTAIN",
            "evidence": [{"seq": 3, "quote": "fever"}],
        },
        cand() | {"unexpected_field": "surprise"},
        cand() | {"evidence": []},
        cand("SYMPTOM", "cough", 3, "No cough"),
    ]
    r = vet(bad)
    assert [v.candidate.text for v in r.kept] == ["cough"] and r.dropped == {"invalid_schema": 4}


def test_unknown_attributes_are_discarded_and_flagged() -> None:
    [v] = vet(
        [cand(attributes={"duration": "3 days", "diagnosis_is": "malaria", "x" * 3: "y"})]
    ).kept
    assert (
        v.candidate.attributes == {"duration": "3 days"} and "unknown_attributes_removed" in v.flags
    )


def test_duplicates_are_removed_within_a_run_and_against_earlier_runs() -> None:
    r = vet([cand(), cand(text="Fever."), cand(text="cough")])
    assert [v.candidate.text for v in r.kept] == ["fever", "cough"] and r.dropped == {
        "duplicate": 1
    }
    key = g.dedupe_key("SYMPTOM", "fever", "PRESENT")
    assert [v.candidate.text for v in vet([cand(), cand(text="cough")], existing={key}).kept] == [
        "cough"
    ]


def test_a_prompt_injection_cannot_add_fields_or_kinds() -> None:
    evil = cand() | {"kind": "PRESCRIBE", "action": "sign prescription"}
    assert vet([evil]).dropped == {"invalid_schema": 1}


@pytest.mark.parametrize(
    "text",
    [
        "I have prescribed amoxicillin",
        "The system ordered a CBC",
        "Patient has been diagnosed with TB",
        "AI started antibiotics",
        "We have referred the patient",
    ],
)
def test_claims_of_autonomous_action_are_detected(text: str) -> None:
    assert g.claims_autonomous_action(text)


@pytest.mark.parametrize(
    "text",
    [
        "Consider an ECG if chest pain persists",
        "Ask about prior prescriptions",
        "Penicillin allergy documented",
    ],
)
def test_ordinary_consideration_language_is_not_flagged(text: str) -> None:
    assert not g.claims_autonomous_action(text)


# ---- the development extractor and registry --------------------------------------------


def run_dev(task: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = LLMRequest(task, "v", "s", "p", payload)
    resp = asyncio.run(DevelopmentLLMProvider().complete(req))
    assert resp.token_counts_are_estimates
    return json.loads(resp.text)  # type: ignore[no-any-return]


def test_dev_extractor_output_is_schema_valid_and_naive_on_purpose() -> None:
    segs = [
        {"seq": s.seq, "speaker_role": s.speaker_role, "language": "en-IN", "text": s.raw_text}
        for s in SEGS
    ]
    out = run_dev("clinical_extraction", {"allowed_kinds": list(ALL_KINDS), "segments": segs})[
        "candidates"
    ]
    for item in out:
        RawCandidate.model_validate(item)
    kinds = {(c["kind"], c["text"], c["assertion"]) for c in out}
    assert ("ALLERGY", "allergy to penicillin", "PRESENT") in kinds  # naive: ignores 'might'
    assert any("?" in c["evidence"][0]["quote"] for c in out)  # naive: quotes the question
    # ...and the guardrails then repair exactly those two weaknesses:
    r = g.vet_candidates(out, SEGS, "CONSULTATION")
    got = {(v.candidate.kind, v.candidate.assertion) for v in r.kept}
    assert ("ALLERGY", "POSSIBLE") in got and ("ALLERGY", "PRESENT") not in got
    assert r.dropped.get("from_question", 0) >= 1


def test_dev_extractor_understands_the_specs_telugu_english_example() -> None:
    text = (
        "Naku two days nunchi fever undi, night time ekkuva avutundi and little breathing problem."
    )
    out = run_dev(
        "clinical_extraction",
        {
            "allowed_kinds": list(ALL_KINDS),
            "segments": [{"seq": 1, "speaker_role": "PATIENT", "language": "te-IN", "text": text}],
        },
    )["candidates"]
    by = {c["text"]: c for c in out}
    assert (
        by["fever"]["attributes"]["duration"] == "2 days"
        and by["fever"]["original_term"] == "fever"
    )
    assert by["breathing difficulty"]["attributes"]["severity"] == "mild"
    assert by["symptoms worse at night"]["attributes"] == {"pattern": "worse at night"}


def test_dev_extractor_ignores_context_only_segments() -> None:
    segs = [
        {
            "seq": 1,
            "speaker_role": "PATIENT",
            "language": "en-IN",
            "text": "I have a cough.",
            "context_only": True,
        }
    ]
    assert (
        run_dev("clinical_extraction", {"allowed_kinds": list(ALL_KINDS), "segments": segs})[
            "candidates"
        ]
        == []
    )


def test_registry_refuses_unbuilt_and_production_dev_llms() -> None:
    assert get_llm("development", environment="test").is_development
    with pytest.raises(LLMUnavailable, match="data-processing agreement"):
        get_llm("anthropic", environment="production")
    assert "anthropic" in PENDING
    with pytest.raises(LLMUnavailable, match="disabled in production"):
        get_llm("development", environment="production")
    with pytest.raises(LLMUnavailable):
        get_llm("", environment="test")


def test_null_providers_admit_they_know_nothing() -> None:
    assert NullTerminologyProvider.available is False
    assert (
        asyncio.run(NullTerminologyProvider().lookup("fever", "SNOMED")) == []
    )  # never invents a code
    for call in (
        NullMedicationKnowledgeProvider().check_interactions(["a", "b"]),
        NullTranslationProvider().translate("x", "en", "hi"),
    ):
        with pytest.raises(NotAvailable):
            asyncio.run(call)


def test_hashing_embeddings_are_deterministic_and_rank_by_overlap() -> None:
    e = HashingEmbeddingProvider()
    a, b, c = asyncio.run(
        e.embed(["chest pain on exertion", "chest pain when walking", "dental hygiene advice"])
    )
    assert asyncio.run(e.embed(["chest pain on exertion"]))[0] == a
    assert cosine(a, b) > cosine(a, c) and cosine(a, a) == pytest.approx(1.0)


def test_the_evaluation_harness_scores_the_bundled_fixtures() -> None:
    import json

    from app.ai.dev_llm import DevelopmentLLMProvider
    from app.ai.eval import DEFAULT_FILE, score

    result = score(json.loads(DEFAULT_FILE.read_text(encoding="utf-8")), DevelopmentLLMProvider())
    assert result["cases"] == 3 and result["negation_accuracy"] is not None
    assert set(result["per_kind"]) >= {"SYMPTOM", "ALLERGY"}
