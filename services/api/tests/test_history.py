from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.db import set_tenant
from tests.clinical_helpers import Visit, get, make_visit, post

H = dict[str, str]


def put(client: TestClient, h: H, url: str, body: dict[str, Any]) -> Any:
    return client.put(f"/api/v1{url}", headers=h, json=body)


@pytest.fixture
def v(client: TestClient, org_a: H) -> Visit:
    return make_visit(client, org_a, stage="consult")


def test_a_doctors_procedure_is_confirmed_and_correctable(client: TestClient, v: Visit) -> None:
    r = post(
        client, v.doctor, f"/encounters/{v.enc_id}/procedures",
        {"display": "Lumbar puncture", "performed_on": "2026-10-01", "body_site": "L4-L5"},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["verification_state"] == "CLINICIAN_CONFIRMED" and p["source"] == "DOCTOR_ENTERED"
    fix = put(client, v.doctor, f"/procedures/{p['id']}", {"outcome": "Clear CSF"})
    assert fix.status_code == 200, fix.text
    assert fix.json()["supersedes_id"] == p["id"] and fix.json()["outcome"] == "Clear CSF"
    hist = get(client, v.doctor, f"/patients/{v.patient['id']}/history").json()
    assert [x["id"] for x in hist["procedures"]] == [fix.json()["id"]]


def test_a_procedure_cannot_be_dated_in_the_future(client: TestClient, v: Visit) -> None:
    r = post(
        client, v.doctor, f"/encounters/{v.enc_id}/procedures",
        {"display": "Biopsy", "performed_on": "2999-01-01"},
    )  # fmt: skip
    assert r.status_code == 422


def test_a_nurse_records_vaccines_that_wait_for_a_doctor(client: TestClient, v: Visit) -> None:
    body = {"vaccine": "Tetanus toxoid", "given_on": "2026-11-01", "dose_number": 1}
    r = post(client, v.nurse, f"/encounters/{v.enc_id}/immunisations", body)
    assert r.status_code == 201, r.text
    assert r.json()["verification_state"] == "UNVERIFIED"
    ok = post(
        client, v.doctor, f"/clinical/immunisations/{r.json()['id']}/verify", {"action": "confirm"}
    )
    assert ok.status_code == 200, ok.text
    hist = get(client, v.nurse, f"/patients/{v.patient['id']}/history").json()
    assert hist["immunisations"][0]["verification_state"] == "CLINICIAN_CONFIRMED"


def test_next_dose_must_follow_the_given_date(client: TestClient, v: Visit) -> None:
    r = post(
        client, v.nurse, f"/encounters/{v.enc_id}/immunisations",
        {"vaccine": "Hepatitis B", "given_on": "2026-11-01", "next_due_on": "2026-10-01"},
    )  # fmt: skip
    assert r.status_code == 422


def test_only_doctors_write_procedures_and_referrals(client: TestClient, v: Visit) -> None:
    for url, body in (
        ("procedures", {"display": "Dressing", "performed_on": "2026-11-01"}),
        ("referrals", {"to_specialty": "Cardiology", "reason": "Chest pain on exertion"}),
    ):
        for who in (v.nurse, v.recep):
            assert post(client, who, f"/encounters/{v.enc_id}/{url}", body).status_code == 403


def test_referral_moves_through_its_states_then_closes(client: TestClient, v: Visit) -> None:
    r = post(
        client, v.doctor, f"/encounters/{v.enc_id}/referrals",
        {"to_specialty": "Cardiology", "reason": "Chest pain on exertion", "urgency": "URGENT"},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    a = put(client, v.doctor, f"/referrals/{r.json()['id']}", {"status": "ACCEPTED"})
    assert a.status_code == 200 and a.json()["status"] == "ACCEPTED"
    c = put(
        client,
        v.doctor,
        f"/referrals/{a.json()['id']}",
        {"status": "COMPLETED", "outcome_note": "Echo normal"},
    )
    assert c.status_code == 200, c.text
    again = put(client, v.doctor, f"/referrals/{c.json()['id']}", {"status": "REQUESTED"})
    assert again.status_code == 400
    hist = get(client, v.doctor, f"/patients/{v.patient['id']}/history").json()
    assert len(hist["referrals"]) == 1 and hist["referrals"][0]["status"] == "COMPLETED"


def test_rows_cannot_be_rewritten_or_deleted_in_sql(
    client: TestClient, v: Visit, db: Session
) -> None:
    r = post(
        client, v.doctor, f"/encounters/{v.enc_id}/procedures",
        {"display": "Dressing", "performed_on": "2026-11-01"},
    )  # fmt: skip
    pid = r.json()["id"]
    set_tenant(db, None, bypass=True)
    for sql in (
        "update procedure_records set display = 'x' where id = :i",
        "delete from procedure_records where id = :i",
    ):
        with pytest.raises(DBAPIError):
            db.execute(text(sql), {"i": pid})
        db.rollback()
        set_tenant(db, None, bypass=True)


def test_history_is_private_to_the_organisation(client: TestClient, v: Visit, org_b: H) -> None:
    post(
        client, v.doctor, f"/encounters/{v.enc_id}/referrals",
        {"to_specialty": "ENT", "reason": "Hearing loss"},
    )  # fmt: skip
    r = get(client, org_b, f"/patients/{v.patient['id']}/history")
    assert r.status_code in (403, 404) or r.json()["referrals"] == []
