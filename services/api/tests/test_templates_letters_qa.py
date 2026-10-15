"""Note templates, referral letters and the cited chart question-and-answer."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.ai import chartqa
from tests.ai_helpers import ai_visit
from tests.clinical_helpers import Visit, get, make_visit, post
from tests.helpers import make_facility, make_practitioner
from tests.test_ai_suggestions import put_json

H = dict[str, str]
TEMPLATE = {
    "name": "Diabetes review",
    "specialty": "Endocrinology",
    "sections": [
        {"note_type": "HPI", "title": "Symptoms", "hint": "Thirst, weight change"},
        {"note_type": "EXAMINATION", "title": "Feet and eyes"},
        {"note_type": "PLAN", "title": "Plan"},
    ],
}


# ---- note templates ----------------------------------------------------------------------------


def test_built_in_layouts_are_available_to_doctors_only(client: TestClient, org_a: H) -> None:
    v = make_visit(client, org_a, stage="consult")
    names = [t["name"] for t in get(client, v.doctor, "/note-templates").json()]
    assert "General consultation" in names and "Follow-up review" in names
    for h in (v.recep,):
        assert get(client, h, "/note-templates").status_code == 403


def test_admins_manage_templates_and_doctors_see_the_active_ones(
    client: TestClient, org_a: H
) -> None:
    v = make_visit(client, org_a, stage="consult")
    assert (
        post(client, v.doctor, "/note-templates", TEMPLATE).status_code == 403
    )  # not theirs to define
    made = post(client, org_a, "/note-templates", TEMPLATE)
    assert made.status_code == 201, made.text
    tid = made.json()["id"]
    assert any(
        t["id"] == tid and not t["builtin"] for t in get(client, v.doctor, "/note-templates").json()
    )
    off = put_json(client, org_a, f"/note-templates/{tid}", {**TEMPLATE, "active": False})
    assert off.status_code == 200
    assert all(t["id"] != tid for t in get(client, v.doctor, "/note-templates").json())
    assert any(t["id"] == tid for t in get(client, org_a, "/note-templates/all").json())


def test_template_sections_are_validated(client: TestClient, org_a: H) -> None:
    bad_type = {**TEMPLATE, "sections": [{"note_type": "TRIAGE", "title": "Triage"}]}
    assert post(client, org_a, "/note-templates", bad_type).status_code == 422  # nurses' notes
    twice = {**TEMPLATE, "sections": [TEMPLATE["sections"][0], {**TEMPLATE["sections"][0]}]}
    assert post(client, org_a, "/note-templates", twice).status_code == 422
    prefilled = {**TEMPLATE, "sections": [{**TEMPLATE["sections"][0], "default": "Normal"}]}
    assert (
        post(client, org_a, "/note-templates", prefilled).status_code == 422
    )  # no pre-filled words
    assert post(client, org_a, "/note-templates", {**TEMPLATE, "sections": []}).status_code == 422


def test_templates_are_private_to_their_organisation_and_audited(
    client: TestClient, org_a: H, org_b: H, db: Session
) -> None:
    made = post(client, org_a, "/note-templates", TEMPLATE).json()
    doctor_b, _ = make_practitioner(client, org_b, "beta-hospital", make_facility(client, org_b))
    assert all(t["id"] != made["id"] for t in get(client, doctor_b, "/note-templates").json())
    assert put_json(client, org_b, f"/note-templates/{made['id']}", TEMPLATE).status_code == 404
    assert (
        db.execute(
            text("select count(*) from audit_logs where action = 'NOTE_TEMPLATE_CREATED'")
        ).scalar()
        == 1
    )


# ---- referral letters --------------------------------------------------------------------------


@pytest.fixture
def v(client: TestClient, org_a: H) -> Visit:
    return make_visit(client, org_a, stage="consult")


def fill(client: TestClient, v: Visit) -> None:
    e = v.enc_id
    post(client, v.nurse, f"/encounters/{e}/vitals", {"heart_rate": 118})
    post(
        client,
        v.nurse,
        f"/encounters/{e}/allergies",
        {
            "substance": "Penicillin",
            "certainty": "POSSIBLE",
            "source": "PATIENT_REPORTED",
            "reaction": "Rash",
        },
    )
    post(
        client,
        v.doctor,
        f"/encounters/{e}/notes",
        {"note_type": "HPI", "content": "Palpitations for two days"},
    )
    post(
        client,
        v.doctor,
        f"/encounters/{e}/conditions",
        {"display": "Possible arrhythmia", "certainty": "SUSPECTED", "category": "DIAGNOSIS"},
    )


def draft(client: TestClient, v: Visit, **kw: Any) -> Any:
    body = {"recipient": "Dr Rao, Cardiology", "reason": "Palpitations needing an ECG review", **kw}
    return post(client, v.doctor, f"/encounters/{v.enc_id}/letters", body)


def test_a_letter_states_what_is_recorded_and_how_certain_it_is(
    client: TestClient, v: Visit
) -> None:
    fill(client, v)
    r = draft(client, v, instructions="Please see within a week.")
    assert r.status_code == 201, r.text
    s = r.json()
    body = s["content"]
    assert (
        s["kind"] == "REFERRAL_LETTER"
        and s["status"] == "DRAFT"
        and s["recipient"] == "Dr Rao, Cardiology"
    )
    assert "To: Dr Rao, Cardiology" in body and "Palpitations needing an ECG review" in body
    assert "Possible arrhythmia (suspected)" in body  # a suspicion is never worded as a diagnosis
    assert "Penicillin (possible, reaction: Rash) (reported by the patient, not verified)" in body
    assert "Palpitations for two days" in body and "Heart Rate: 118" in body
    assert "Please see within a week." in body
    assert "address" not in body.lower()


def test_allergy_status_is_never_silent_in_a_letter(client: TestClient, v: Visit) -> None:
    assert "allergy status has not been recorded" in draft(client, v).json()["content"]
    post(client, v.doctor, f"/encounters/{v.enc_id}/allergies", {"is_nka": True})
    assert "no known allergies recorded" in draft(client, v).json()["content"]


def test_letters_and_summaries_are_numbered_and_superseded_separately(
    client: TestClient, v: Visit
) -> None:
    first = draft(client, v).json()
    summary = post(
        client, v.doctor, f"/encounters/{v.enc_id}/summaries", {"instructions": "Rest."}
    ).json()
    assert first["version"] == 1 and summary["version"] == 1
    edited = put_json(
        client, v.doctor, f"/summaries/{first['id']}", {"content": "Edited by the doctor."}
    )
    assert edited.json()["content"] == "Edited by the doctor."
    assert (
        post(client, v.doctor, f"/summaries/{first['id']}/approve").json()["status"] == "APPROVED"
    )
    assert post(client, v.doctor, f"/summaries/{summary['id']}/approve").status_code == 200
    second = draft(client, v).json()
    post(client, v.doctor, f"/summaries/{second['id']}/approve")
    rows = {
        (r["kind"], r["version"]): r["status"]
        for r in get(client, v.doctor, f"/encounters/{v.enc_id}/summaries").json()
    }
    assert rows == {
        ("REFERRAL_LETTER", 1): "SUPERSEDED",
        ("REFERRAL_LETTER", 2): "APPROVED",
        ("VISIT_SUMMARY", 1): "APPROVED",  # approving a letter never touches the patient summary
    }


def test_a_letter_to_a_different_recipient_does_not_supersede_the_first(
    client: TestClient, v: Visit
) -> None:
    a = draft(client, v).json()
    b = draft(client, v, recipient="Dr Iyer, Neurology").json()
    post(client, v.doctor, f"/summaries/{a['id']}/approve")
    post(client, v.doctor, f"/summaries/{b['id']}/approve")
    states = {
        r["recipient"]: r["status"]
        for r in get(client, v.doctor, f"/encounters/{v.enc_id}/summaries").json()
    }
    assert states == {"Dr Rao, Cardiology": "APPROVED", "Dr Iyer, Neurology": "APPROVED"}


def test_only_the_treating_doctor_writes_letters(client: TestClient, v: Visit, org_a: H) -> None:
    for h in (v.nurse, v.recep):
        assert (
            post(
                client,
                h,
                f"/encounters/{v.enc_id}/letters",
                {"recipient": "Dr X", "reason": "Because"},
            ).status_code
            == 403
        )
    other, _ = make_practitioner(
        client, org_a, "alpha-clinic", v.facility, "dr.other@x.example.com"
    )
    assert (
        post(
            client,
            other,
            f"/encounters/{v.enc_id}/letters",
            {"recipient": "Dr X", "reason": "Because"},
        ).status_code
        == 403
    )


def test_an_approved_letter_cannot_be_changed_even_with_sql(
    client: TestClient, v: Visit, db: Session
) -> None:
    from sqlalchemy.exc import DBAPIError

    s = draft(client, v).json()
    post(client, v.doctor, f"/summaries/{s['id']}/approve")
    with pytest.raises(DBAPIError):
        db.execute(
            text(
                "update patient_summaries set recipient = 'Someone else' where status = 'APPROVED'"
            )
        )
        db.commit()
    db.rollback()


# ---- chart question and answer -----------------------------------------------------------------


@pytest.fixture
def ai(client: TestClient, org_a: H) -> Visit:
    visit = ai_visit(client, org_a)
    fill(client, visit)
    post(
        client,
        visit.doctor,
        f"/encounters/{visit.enc_id}/conditions",
        {"display": "Type 2 diabetes", "certainty": "CONFIRMED", "category": "PROBLEM"},
    )
    return visit


def ask(client: TestClient, v: Visit, question: str, h: H | None = None) -> Any:
    return post(
        client, h or v.doctor, f"/patients/{v.patient['id']}/ai/ask", {"question": question}
    )


def test_an_answer_cites_the_chart_entries_it_rests_on(client: TestClient, ai: Visit) -> None:
    r = ask(client, ai, "What allergies does the patient have, penicillin?")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["used_ai"] and out["answered"] and out["is_development"]
    first = out["answer"][0]
    assert "Penicillin" in first["text"] and first["citations"]
    assert all(c["ref"].startswith("allergy:") for c in first["citations"])
    assert out["matches"] and "Penicillin" in out["matches"][0]["text"]


def test_a_question_the_chart_cannot_answer_says_so_instead_of_guessing(
    client: TestClient, ai: Visit
) -> None:
    out = ask(client, ai, "Has the patient ever had a kidney transplant?").json()
    assert out["used_ai"] and out["answered"] is False and out["answer"] == []
    assert "could not be answered" in out["message"]


def test_without_ai_consent_it_falls_back_to_a_plain_search(client: TestClient, org_a: H) -> None:
    visit = make_visit(client, org_a, stage="consult")
    fill(client, visit)
    on = put_json(
        client,
        org_a,
        "/organisations/current/policy",
        {"recording_enabled": True, "ai_processing_enabled": True},
    )
    assert on.status_code == 200  # the organisation allows it; this patient has not consented
    out = ask(client, visit, "penicillin allergy").json()
    assert out["used_ai"] is False and out["answer"] is None
    assert any("Penicillin" in m["text"] for m in out["matches"])
    assert "consent" in out["message"]


def test_with_the_organisation_switch_off_nothing_goes_to_a_model(
    client: TestClient, ai: Visit, org_a: H
) -> None:
    off = put_json(
        client,
        org_a,
        "/organisations/current/policy",
        {"recording_enabled": True, "ai_processing_enabled": False},
    )
    assert off.status_code == 200
    out = ask(client, ai, "penicillin").json()
    assert out["used_ai"] is False and "not switched on" in out["message"]


def test_unreviewed_ai_output_is_not_part_of_the_chart(
    client: TestClient, ai: Visit, db: Session
) -> None:
    from tests.ai_helpers import PATIENT, ai_interaction, analyse, say

    iid = ai_interaction(client, ai)
    say(db, iid, [(PATIENT, "I have had fever for three days.")])
    assert analyse(client, ai.doctor, iid).json()["new_candidates"] >= 1  # pending, unreviewed
    out = ask(client, ai, "any fever recorded").json()
    assert out["matches"] == [] and out["answer"] == []


def test_questions_are_audited_and_metered_without_their_text(
    client: TestClient, ai: Visit, db: Session
) -> None:
    ask(client, ai, "penicillin allergy secret-question-text")
    rows = db.execute(
        text("select action, ai_involved from audit_logs where action = 'AI_CHART_QUESTION'")
    ).all()
    assert [tuple(r) for r in rows] == [("AI_CHART_QUESTION", True)]
    assert "secret-question-text" not in str(db.execute(text("select * from audit_logs")).all())
    usage = db.execute(text("select feature, status from ai_usage")).all()
    assert [tuple(u) for u in usage] == [("chart_qa", "OK")]


def test_access_rate_limit_and_tenant_rules(client: TestClient, ai: Visit, org_b: H) -> None:
    assert ask(client, ai, "penicillin", ai.recep).status_code == 403
    doctor_b, _ = make_practitioner(client, org_b, "beta-hospital", make_facility(client, org_b))
    assert ask(client, ai, "penicillin", doctor_b).status_code == 404
    client.app.state.settings.ai_analyses_per_minute = 2  # type: ignore[attr-defined]
    try:
        codes = [ask(client, ai, "penicillin allergy").status_code for _ in range(3)]
    finally:
        client.app.state.settings.ai_analyses_per_minute = 6  # type: ignore[attr-defined]
    assert codes == [200, 200, 429]


# ---- vetting of model answers (no database) ----------------------------------------------------

ITEMS = [{"ref": "allergy:1", "text": "Allergy: Penicillin (possible)", "date": "2026-10-01"}]


def test_uncited_or_wrongly_cited_statements_are_dropped() -> None:
    kept, why = chartqa.vet_statements(
        [
            {"text": "Allergic to penicillin.", "refs": ["allergy:1"]},
            {"text": "Also on warfarin.", "refs": []},
            {"text": "Takes insulin.", "refs": ["med:999"]},
            {"text": "I have prescribed amoxicillin.", "refs": ["allergy:1"]},
            {"text": "x", "refs": ["allergy:1"], "extra": 1},
        ],
        ITEMS,
    )
    assert [k.text for k in kept] == ["Allergic to penicillin."]
    assert why == {"invalid": 2, "unknown_citation": 1, "claims_action": 1}
    assert kept[0].citations[0].label.startswith("Allergy: Penicillin")
