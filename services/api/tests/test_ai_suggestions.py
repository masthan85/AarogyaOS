"""Decision support, reference knowledge and patient summaries against a real database."""

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.modules.ai import suggestions
from app.modules.ai.models import AiSuggestion
from tests.ai_helpers import DOCTOR, PATIENT, ai_interaction, ai_visit, analyse, say
from tests.clinical_helpers import Visit, get, post
from tests.conftest import make_staff

H = dict[str, str]
GUIDE = {
    "title": "Fever in adults (synthetic test document)",
    "publisher": "Test Publisher",
    "source": "synthetic",
    "version": "1",
    "licence": "SYNTHETIC_TEST",
    "chunks": [
        "Fever lasting more than three days in an adult should prompt a search for a source.",
        "Hypertension targets are reviewed at every visit.",
    ],
}


def put_json(client: TestClient, h: H, url: str, body: dict[str, Any]) -> Any:
    return client.put(f"/api/v1{url}", headers=h, json=body)


def suggest(client: TestClient, v: Visit) -> dict[str, Any]:
    r = post(client, v.doctor, f"/encounters/{v.enc_id}/ai/suggestions")
    assert r.status_code == 200, r.text
    return r.json()


def listed(client: TestClient, v: Visit) -> list[dict[str, Any]]:
    r = get(client, v.doctor, f"/encounters/{v.enc_id}/ai/suggestions")
    assert r.status_code == 200, r.text
    return list(r.json())


def approved_guide(client: TestClient, org: H) -> str:
    r = post(client, org, "/knowledge/documents", GUIDE)
    assert r.status_code == 201, r.text
    other = make_staff(
        client, org, "admin2@alpha-clinic.example.com", "clinic_admin", "alpha-clinic"
    )[0]
    a = post(client, other, f"/knowledge/documents/{r.json()['id']}/approve")
    assert a.status_code == 200, a.text
    return str(r.json()["id"])


@pytest.fixture
def v(client: TestClient, org_a: H) -> Visit:
    return ai_visit(client, org_a, suggestions=True)


def test_rule_based_suggestions_need_no_model_and_change_nothing(
    client: TestClient, v: Visit, db: Session
) -> None:
    out = suggest(client, v)
    assert out["created"] >= 2
    cats = {s["category"] for s in listed(client, v)}
    assert {"IMPORTANT_INFORMATION", "MISSING_HISTORY_QUESTION"} <= cats
    assert all(s["origin"] in ("DETERMINISTIC", "MODEL") for s in listed(client, v))
    for table in ("conditions", "allergies", "service_requests", "prescriptions"):
        assert db.execute(text(f"select count(*) from {table}")).scalar() == 0  # noqa: S608


def test_running_it_again_does_not_repeat_suggestions(client: TestClient, v: Visit) -> None:
    suggest(client, v)
    n = len(listed(client, v))
    assert suggest(client, v)["created"] == 0
    assert len(listed(client, v)) == n


def test_it_is_off_unless_the_organisation_enables_it(client: TestClient, org_a: H) -> None:
    v = ai_visit(client, org_a, suggestions=False)
    assert post(client, v.doctor, f"/encounters/{v.enc_id}/ai/suggestions").status_code == 409


def test_without_ai_consent_only_the_rules_run(client: TestClient, org_a: H) -> None:
    from tests.clinical_helpers import make_visit
    from tests.speech_helpers import enable_recording, install_wording

    v = make_visit(client, org_a, stage="consult")
    enable_recording(client, org_a, ai=True)
    put_json(
        client,
        org_a,
        "/organisations/current/policy",
        {"recording_enabled": True, "ai_processing_enabled": True, "ai_suggestions_enabled": True},
    )
    install_wording(client, org_a)
    out = suggest(client, v)
    assert out["model_used"] is False and out["created"] >= 1


def test_a_discussed_medicine_that_clashes_with_a_recorded_allergy_is_flagged(
    client: TestClient, v: Visit, db: Session
) -> None:
    post(
        client,
        v.nurse,
        f"/encounters/{v.enc_id}/allergies",
        {"substance": "Penicillin", "certainty": "CONFIRMED", "source": "PATIENT_REPORTED"},
    )
    iid = ai_interaction(client, v)
    say(db, iid, [(DOCTOR, "I will start penicillin."), (PATIENT, "Okay.")])
    from app.modules.ai.models import AiCandidate, AiExtraction
    from app.modules.interactions.models import ClinicalInteraction

    ia = db.get(ClinicalInteraction, uuid.UUID(iid))
    assert ia is not None
    run = AiExtraction(
        organisation_id=ia.organisation_id,
        interaction_id=ia.id,
        patient_id=ia.patient_id,
        encounter_id=ia.encounter_id,
        triggered_by=ia.started_by,
        prompt_version="x",
        provider="development",
        model="m",
        is_development=True,
        from_seq=1,
        to_seq=2,
        status="OK",
    )
    db.add(run)
    db.flush()
    db.add(
        AiCandidate(
            organisation_id=ia.organisation_id,
            extraction_id=run.id,
            interaction_id=ia.id,
            patient_id=ia.patient_id,
            encounter_id=ia.encounter_id,
            kind="TREATMENT_DISCUSSED",
            text="penicillin",
            assertion="PRESENT",
            dedupe_key="t|penicillin",
        )
    )
    db.commit()
    suggest(client, v)
    warn = [s for s in listed(client, v) if s["category"] == "ALLERGY_WARNING"]
    assert (
        warn and warn[0]["origin"] == "DETERMINISTIC" and "penicillin" in warn[0]["title"].lower()
    )


def test_unapproved_reference_material_is_never_used(
    client: TestClient, org_a: H, v: Visit, db: Session
) -> None:
    r = post(client, org_a, "/knowledge/documents", GUIDE)
    assert r.status_code == 201 and r.json()["approved"] is False
    iid = ai_interaction(client, v)
    say(db, iid, [(PATIENT, "I have had fever for three days.")])
    analyse(client, v.doctor, iid)
    suggest(client, v)
    assert not [s for s in listed(client, v) if s["category"] == "GUIDELINE"]


def test_approved_reference_material_is_cited_with_its_source(
    client: TestClient, org_a: H, v: Visit, db: Session
) -> None:
    approved_guide(client, org_a)
    iid = ai_interaction(client, v)
    say(db, iid, [(PATIENT, "I have had fever for three days.")])
    analyse(client, v.doctor, iid)
    out = suggest(client, v)
    assert out["model_used"] is True
    g = [s for s in listed(client, v) if s["category"] == "GUIDELINE"]
    assert g and g[0]["origin"] == "MODEL" and g[0]["provider"] == "development"
    src = g[0]["evidence_sources"][0]
    assert src["document"].startswith("Fever in adults") and src["version"] == "1"


def test_a_document_cannot_be_approved_by_the_person_who_added_it(
    client: TestClient, org_a: H
) -> None:
    r = post(client, org_a, "/knowledge/documents", GUIDE)
    assert post(client, org_a, f"/knowledge/documents/{r.json()['id']}/approve").status_code == 403


def test_a_retired_document_stops_being_used(
    client: TestClient, org_a: H, v: Visit, db: Session
) -> None:
    doc = approved_guide(client, org_a)
    assert post(client, org_a, f"/knowledge/documents/{doc}/retire").status_code == 200
    iid = ai_interaction(client, v)
    say(db, iid, [(PATIENT, "I have had fever for three days.")])
    analyse(client, v.doctor, iid)
    suggest(client, v)
    assert not [s for s in listed(client, v) if s["category"] == "GUIDELINE"]


def test_doctors_cannot_manage_knowledge_but_can_read_it(client: TestClient, v: Visit) -> None:
    assert post(client, v.doctor, "/knowledge/documents", GUIDE).status_code == 403
    assert get(client, v.doctor, "/knowledge/documents").status_code == 200


# ---- vetting of model output (no database needed) --------------------------------------


def _ctx(allergy: str | None = None, medicine: str | None = None) -> Any:
    return SimpleNamespace(
        allergies=[SimpleNamespace(substance=allergy, is_nka=False)] if allergy else [],
        medications=[SimpleNamespace(name=medicine)] if medicine else [],
    )


HIT = SimpleNamespace(chunk_id="c1", title="Doc", publisher="P", version="1", text="passage")


def vet(items: list[dict[str, Any]], ctx: Any = None, require_source: bool = True):  # type: ignore[no-untyped-def]
    return suggestions._vet_model_items(  # noqa: SLF001
        items, {"note:1"}, {"c1": HIT}, ctx or _ctx(), require_source
    )


def item(**kw: Any) -> dict[str, Any]:
    base = {
        "category": "GUIDELINE",
        "title": "Consider a review",
        "explanation": "Reference suggests a review.",
        "source_chunk_ids": ["c1"],
    }
    return {**base, **kw}


def test_vetting_drops_what_it_cannot_trust() -> None:
    kept, why = vet(
        [
            item(),
            item(category="INTERACTION", title="Interaction found"),
            item(title="Another", supporting_refs=["made:up"]),
            item(title="Third", source_chunk_ids=["nope"]),
            item(title="Fourth", source_chunk_ids=[]),
            item(title="Fifth", explanation="I have prescribed amoxicillin."),
            {"category": "GUIDELINE", "nonsense": True},
        ]
    )
    assert len(kept) == 1
    assert why == {
        "safety_category_from_model": 1,
        "unknown_reference": 1,
        "unknown_source": 1,
        "no_source": 1,
        "claims_action": 1,
        "invalid": 1,
    }


def test_sources_are_optional_only_when_the_organisation_says_so() -> None:
    kept, _ = vet([item(source_chunk_ids=[])], require_source=False)
    assert len(kept) == 1


def test_context_only_categories_do_not_need_a_reference_source() -> None:
    kept, _ = vet(
        [item(category="MISSING_HISTORY_QUESTION", source_chunk_ids=[], supporting_refs=["note:1"])]
    )
    assert len(kept) == 1


def test_a_model_suggestion_touching_an_allergy_becomes_a_warning() -> None:
    kept, _ = vet(
        [item(category="MEDICATION_CONSIDERATION", medicine_name="Penicillin V")],
        _ctx(allergy="penicillin"),
    )
    assert kept[0]["category"] == "ALLERGY_WARNING" and kept[0]["warnings"]


def test_duplicate_therapy_is_noted() -> None:
    kept, _ = vet(
        [item(category="MEDICATION_CONSIDERATION", medicine_name="Metformin")],
        _ctx(medicine="metformin"),
    )
    assert "already recorded" in kept[0]["warnings"][0]


# ---- acting on suggestions --------------------------------------------------------------


def add_suggestion(db: Session, v: Visit, **kw: Any) -> str:
    from app.modules.clinical.models import Encounter

    enc = db.get(Encounter, uuid.UUID(v.enc_id))
    assert enc is not None
    row = AiSuggestion(
        organisation_id=enc.organisation_id,
        patient_id=enc.patient_id,
        encounter_id=enc.id,
        category=kw.get("category", "INVESTIGATION"),
        title="Consider a blood test",
        explanation="Reference suggests a full blood count.",
        origin="MODEL",
        payload=kw.get("payload", {"test": "Full blood count", "category": "LAB"}),
        dedupe_key=f"k{uuid.uuid4()}",
    )
    db.add(row)
    db.commit()
    return str(row.id)


def act(client: TestClient, h: H, sid: str, action: str, **kw: Any) -> Any:
    return post(client, h, f"/ai/suggestions/{sid}/action", {"action": action, **kw})


def test_accepting_an_investigation_suggestion_creates_only_a_draft_order(
    client: TestClient, v: Visit, db: Session
) -> None:
    sid = add_suggestion(db, v)
    r = act(client, v.doctor, sid, "accept")
    assert r.status_code == 200, r.text
    assert r.json()["result_kind"] == "service_requests"
    row = db.execute(text("select status, source from service_requests")).one()
    assert tuple(row) == ("DRAFT", "AI_EXTRACTED")
    assert act(client, v.doctor, sid, "accept").status_code == 409


def test_other_acceptances_are_acknowledgements_that_create_no_record(
    client: TestClient, v: Visit, db: Session
) -> None:
    sid = add_suggestion(db, v, category="DIFFERENTIAL", payload={})
    assert act(client, v.doctor, sid, "accept").json()["result_id"] is None
    assert db.execute(text("select count(*) from conditions")).scalar() == 0


def test_edit_reject_and_dismiss_are_recorded(client: TestClient, v: Visit, db: Session) -> None:
    a, b, c = (add_suggestion(db, v, category="GUIDELINE", payload={}) for _ in range(3))
    assert act(client, v.doctor, a, "edit").status_code == 400
    assert (
        act(client, v.doctor, a, "edit", title="Better title").json()["suggestion"]["status"]
        == "EDITED"
    )
    assert (
        act(client, v.doctor, b, "reject", reason="not relevant").json()["suggestion"]["status"]
        == "REJECTED"
    )
    assert act(client, v.doctor, c, "dismiss").json()["suggestion"]["status"] == "DISMISSED"
    actions = (
        db.execute(text("select action from ai_suggestion_actions order by created_at"))
        .scalars()
        .all()
    )
    assert sorted(actions) == ["DISMISS", "EDIT", "REJECT"]


def test_only_the_encounters_doctor_can_see_or_act(
    client: TestClient, v: Visit, org_a: H, db: Session
) -> None:
    sid = add_suggestion(db, v)
    assert act(client, v.nurse, sid, "accept").status_code == 403
    assert get(client, v.nurse, f"/encounters/{v.enc_id}/ai/suggestions").status_code == 403
    assert act(client, v.recep, sid, "accept").status_code == 403


def test_suggestions_are_tenant_isolated_and_their_content_is_immutable(
    client: TestClient, v: Visit, org_b: H, db: Session
) -> None:
    from tests.helpers import make_facility, make_practitioner

    sid = add_suggestion(db, v)
    doctor_b, _ = make_practitioner(client, org_b, "beta-hospital", make_facility(client, org_b))
    assert act(client, doctor_b, sid, "reject").status_code == 404
    for sql in (
        "update ai_suggestions set category = 'GUIDELINE'",
        "update ai_suggestions set origin = 'DETERMINISTIC'",
        "delete from ai_suggestions",
    ):
        with pytest.raises(DBAPIError):
            db.execute(text(sql))
            db.commit()
        db.rollback()


def test_ai_usage_is_metered_without_content(
    client: TestClient, org_a: H, v: Visit, db: Session
) -> None:
    iid = ai_interaction(client, v)
    say(db, iid, [(PATIENT, "I have had fever for three days.")])
    analyse(client, v.doctor, iid)
    rows = get(client, org_a, "/usage/ai").json()
    assert rows and rows[0]["feature"] == "extraction" and rows[0]["calls"] == 1
    assert rows[0]["tokens_are_estimates"] is True and rows[0]["estimated_cost_paise"] is None
    assert "fever" not in str(rows).lower()


# ---- patient summaries --------------------------------------------------------------------


def test_summary_contains_only_recorded_data_and_the_doctors_instructions(
    client: TestClient, v: Visit, db: Session
) -> None:
    iid = ai_interaction(client, v)
    say(db, iid, [(PATIENT, "I have had fever for three days.")])
    analyse(client, v.doctor, iid)  # pending, unreviewed
    r = post(
        client,
        v.doctor,
        f"/encounters/{v.enc_id}/summaries",
        {"instructions": "Drink plenty of fluids."},
    )
    assert r.status_code == 201, r.text
    s = r.json()
    assert "Drink plenty of fluids." in s["content"] and "fever" not in s["content"].lower()
    assert s["status"] == "DRAFT" and s["translation_status"] == "NOT_NEEDED"


def test_a_translation_that_is_not_available_is_declared_not_faked(
    client: TestClient, v: Visit
) -> None:
    r = post(
        client,
        v.doctor,
        f"/encounters/{v.enc_id}/summaries",
        {"language": "hi-IN", "instructions": "Rest."},
    )
    s = r.json()
    assert s["translation_status"] == "NOT_AVAILABLE" and s["language"] == "en-IN"


def test_approval_supersedes_and_freezes_the_summary(
    client: TestClient, v: Visit, db: Session
) -> None:
    first = post(
        client, v.doctor, f"/encounters/{v.enc_id}/summaries", {"instructions": "One."}
    ).json()
    assert (
        put_json(client, v.doctor, f"/summaries/{first['id']}", {"content": "Edited text."}).json()[
            "content"
        ]
        == "Edited text."
    )
    assert (
        post(client, v.doctor, f"/summaries/{first['id']}/approve").json()["status"] == "APPROVED"
    )
    assert (
        put_json(client, v.doctor, f"/summaries/{first['id']}", {"content": "x"}).status_code == 409
    )
    second = post(
        client, v.doctor, f"/encounters/{v.enc_id}/summaries", {"instructions": "Two."}
    ).json()
    post(client, v.doctor, f"/summaries/{second['id']}/approve")
    states = {
        s["version"]: s["status"]
        for s in get(client, v.doctor, f"/encounters/{v.enc_id}/summaries").json()
    }
    assert states == {1: "SUPERSEDED", 2: "APPROVED"}
    with pytest.raises(DBAPIError):
        db.execute(
            text("update patient_summaries set content = 'tampered' where status = 'APPROVED'")
        )
        db.commit()
    db.rollback()


def test_nurses_and_receptionists_cannot_write_summaries(client: TestClient, v: Visit) -> None:
    assert post(client, v.recep, f"/encounters/{v.enc_id}/summaries", {}).status_code == 403
    assert post(client, v.nurse, f"/encounters/{v.enc_id}/summaries", {}).status_code == 403
