"""Analysis and candidate review against a real database."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.ai_helpers import DOCTOR, PATIENT, ai_interaction, ai_visit, analyse, say
from tests.clinical_helpers import get, post

H = dict[str, str]
CONSULT = [
    (DOCTOR, "What brings you in today?"),
    (PATIENT, "I have had fever for three days."),
    (DOCTOR, "Do you have chest pain?"),
    (PATIENT, "No, I do not have chest pain. I am allergic to penicillin."),
]


def cands(client: TestClient, h: H, iid: str) -> list[dict[str, Any]]:
    r = get(client, h, f"/interactions/{iid}/ai/candidates")
    assert r.status_code == 200, r.text
    return list(r.json())


def test_analysis_produces_grounded_candidates_and_writes_nothing_to_the_record(
    client: TestClient, org_a: H, db: Session
) -> None:
    v = ai_visit(client, org_a)
    iid = ai_interaction(client, v)
    say(db, iid, CONSULT)
    r = analyse(client, v.doctor, iid)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "OK" and r.json()["is_development"] is True
    found = cands(client, v.doctor, iid)
    by_text = {c["text"]: c for c in found}
    assert by_text["fever"]["assertion"] == "PRESENT"
    assert by_text["chest pain"]["assertion"] == "ABSENT"
    assert all(c["status"] == "PENDING" and c["evidence"] for c in found)
    # the doctor's question is never turned into a finding
    assert all(e["speaker_role"] != "DOCTOR" for c in found for e in c["evidence"])
    for table in ("conditions", "allergies", "clinical_notes", "patient_medications"):
        assert db.execute(text(f"select count(*) from {table}")).scalar() == 0  # noqa: S608


def test_a_second_run_with_nothing_new_changes_nothing(
    client: TestClient, org_a: H, db: Session
) -> None:
    v = ai_visit(client, org_a)
    iid = ai_interaction(client, v)
    say(db, iid, CONSULT)
    assert analyse(client, v.doctor, iid).json()["status"] == "OK"
    n = len(cands(client, v.doctor, iid))
    again = analyse(client, v.doctor, iid)
    assert again.json()["status"] == "NOTHING_NEW"
    assert len(cands(client, v.doctor, iid)) == n


def test_analysis_needs_ai_consent_policy_and_permission(
    client: TestClient, org_a: H, db: Session
) -> None:
    v = ai_visit(client, org_a)
    iid = ai_interaction(client, v)
    say(db, iid, CONSULT)
    assert analyse(client, v.recep, iid).status_code == 403
    r = post(
        client,
        v.recep,
        f"/patients/{v.patient['id']}/consents/withdraw",
        {"purpose": "AI_PROCESSING"},
    )
    if r.status_code in (200, 201):
        again = analyse(client, v.doctor, iid)
        assert again.status_code in (403, 409)
    off = client.put(
        "/api/v1/organisations/current/policy",
        headers=org_a,
        json={
            "recording_enabled": True,
            "ai_processing_enabled": False,
            "ai_suggestions_enabled": False,
        },
    )
    assert off.status_code == 200
    assert analyse(client, v.doctor, iid).status_code == 409


def test_accepting_a_symptom_creates_a_traceable_ai_sourced_fact(
    client: TestClient, org_a: H, db: Session
) -> None:
    v = ai_visit(client, org_a)
    iid = ai_interaction(client, v)
    say(db, iid, CONSULT)
    analyse(client, v.doctor, iid)
    fever = next(c for c in cands(client, v.doctor, iid) if c["text"] == "fever")
    r = post(client, v.doctor, f"/ai/candidates/{fever['id']}/review", {"action": "accept"})
    assert r.status_code == 200, r.text
    assert r.json()["candidate"]["status"] == "ACCEPTED" and r.json()["result_id"]
    facts = db.execute(
        text(
            "select source, verification_state, evidence_segment_ids from observations "
            "union all select source, verification_state, evidence_segment_ids from conditions "
            "union all select source, verification_state, evidence_segment_ids from clinical_notes"
        )
    ).all()
    assert any(
        f[0] == "AI_EXTRACTED" and f[1] in ("CLINICIAN_CONFIRMED", "EDITED") and f[2] for f in facts
    )
    again = post(client, v.doctor, f"/ai/candidates/{fever['id']}/review", {"action": "accept"})
    assert again.status_code == 409


def test_edit_requires_wording_and_is_recorded_as_edited(
    client: TestClient, org_a: H, db: Session
) -> None:
    v = ai_visit(client, org_a)
    iid = ai_interaction(client, v)
    say(db, iid, CONSULT)
    analyse(client, v.doctor, iid)
    fever = next(c for c in cands(client, v.doctor, iid) if c["text"] == "fever")
    url = f"/ai/candidates/{fever['id']}/review"
    assert post(client, v.doctor, url, {"action": "edit"}).status_code == 400
    r = post(client, v.doctor, url, {"action": "edit", "edited_text": "high-grade fever"})
    assert r.status_code == 200, r.text
    assert r.json()["candidate"]["status"] == "EDITED"


def test_rejecting_records_the_decision_and_creates_no_fact(
    client: TestClient, org_a: H, db: Session
) -> None:
    v = ai_visit(client, org_a)
    iid = ai_interaction(client, v)
    say(db, iid, CONSULT)
    analyse(client, v.doctor, iid)
    first = cands(client, v.doctor, iid)[0]
    r = post(client, v.doctor, f"/ai/candidates/{first['id']}/review", {"action": "reject"})
    assert r.status_code == 200 and r.json()["result_id"] is None
    assert db.execute(text("select count(*) from conditions")).scalar() == 0


def test_a_nurse_cannot_accept_doctor_only_kinds(client: TestClient, org_a: H, db: Session) -> None:
    v = ai_visit(client, org_a)
    iid = ai_interaction(client, v)
    say(db, iid, [(PATIENT, "I am allergic to penicillin."), (PATIENT, "I take metformin daily.")])
    analyse(client, v.doctor, iid)
    for c in cands(client, v.doctor, iid):
        r = post(client, v.nurse, f"/ai/candidates/{c['id']}/review", {"action": "accept"})
        assert r.status_code in (403, 404), (c["kind"], r.text)


def test_review_decisions_are_final_even_with_sql(
    client: TestClient, org_a: H, db: Session
) -> None:
    import pytest
    from sqlalchemy.exc import DBAPIError

    v = ai_visit(client, org_a)
    iid = ai_interaction(client, v)
    say(db, iid, CONSULT)
    analyse(client, v.doctor, iid)
    c = cands(client, v.doctor, iid)[0]
    post(client, v.doctor, f"/ai/candidates/{c['id']}/review", {"action": "reject"})
    for sql in (
        "update ai_candidates set status = 'ACCEPTED'",
        "update ai_candidates set text = 'x'",
        "delete from ai_candidates",
    ):
        with pytest.raises(DBAPIError):
            db.execute(text(sql))
            db.commit()
        db.rollback()


def test_other_organisations_cannot_see_or_review_candidates(
    client: TestClient, org_a: H, org_b: H, db: Session
) -> None:
    from tests.helpers import make_facility, make_practitioner

    v = ai_visit(client, org_a)
    iid = ai_interaction(client, v)
    say(db, iid, CONSULT)
    analyse(client, v.doctor, iid)
    cid = cands(client, v.doctor, iid)[0]["id"]
    doctor_b, _ = make_practitioner(client, org_b, "beta-hospital", make_facility(client, org_b))
    assert get(client, doctor_b, f"/interactions/{iid}/ai/candidates").status_code == 404
    assert analyse(client, doctor_b, iid).status_code == 404
    assert (
        post(client, doctor_b, f"/ai/candidates/{cid}/review", {"action": "reject"}).status_code
        == 404
    )
