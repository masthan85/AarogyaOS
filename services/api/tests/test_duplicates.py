"""A double tap, a retried request or two staff acting at once must not create two of anything that
should exist once: a patient's visit in the queue, or a draft prescription."""

import threading
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.clinical_helpers import get, make_visit, post, rx_body
from tests.helpers import make_facility, make_patient, make_practitioner, reception

H = dict[str, str]
ORG = "alpha-clinic"


def walk_in(
    client: TestClient,
    h: H,
    patient: dict[str, Any],
    facility: dict[str, Any],
    key: str | None = None,
) -> Any:
    headers = {**h, "Idempotency-Key": key} if key else h
    return client.post(
        "/api/v1/walk-ins",
        headers=headers,
        json={"patient_id": patient["id"], "facility_id": facility["id"]},
    )


@pytest.fixture
def desk(client: TestClient, org_a: H) -> tuple[H, dict[str, Any], dict[str, Any]]:
    facility = make_facility(client, org_a)
    make_practitioner(client, org_a, ORG, facility)
    recep = reception(client, org_a, ORG)
    patient = make_patient(client, recep, "Meera Pillai")
    return recep, facility, patient


def test_a_repeated_walk_in_with_the_same_key_returns_the_same_visit(
    client: TestClient, desk: tuple[H, dict[str, Any], dict[str, Any]]
) -> None:
    recep, facility, patient = desk
    key = "walk-" + uuid.uuid4().hex
    first = walk_in(client, recep, patient, facility, key)
    again = walk_in(client, recep, patient, facility, key)
    assert first.status_code == 201 and again.status_code == 201, again.text
    assert again.json()["id"] == first.json()["id"]
    assert again.json()["token_number"] == first.json()["token_number"]
    queue = get(client, recep, "/queue", facility_id=facility["id"]).json()
    assert [q["patient_id"] for q in queue] == [patient["id"]]


def test_two_walk_ins_racing_each_other_still_make_one_visit(
    client: TestClient, desk: tuple[H, dict[str, Any], dict[str, Any]]
) -> None:
    recep, facility, patient = desk
    codes: list[int] = []

    def send() -> None:
        codes.append(walk_in(client, recep, patient, facility).status_code)

    threads = [threading.Thread(target=send) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # One is checked in; every other request is told so. None fails with a server error.
    assert sorted(codes) == [201, 409, 409, 409]
    queue = get(client, recep, "/queue", facility_id=facility["id"]).json()
    assert len(queue) == 1


def test_the_database_refuses_a_second_active_visit_for_a_patient(
    client: TestClient, desk: tuple[H, dict[str, Any], dict[str, Any]], db: Session
) -> None:
    recep, facility, patient = desk
    assert walk_in(client, recep, patient, facility).status_code == 201
    with pytest.raises(IntegrityError, match="uq_appointments_one_active_visit"):
        db.execute(
            text(
                "insert into appointments (id, organisation_id, patient_id, facility_id, kind, "
                "status, start_at, end_at, booked_by) select gen_random_uuid(), organisation_id, "
                "patient_id, facility_id, kind, 'WAITING', start_at, end_at, booked_by "
                "from appointments where patient_id = :p"
            ),
            {"p": patient["id"]},
        )
    db.rollback()


def test_a_repeated_prescription_request_returns_the_first_draft(
    client: TestClient, org_a: H
) -> None:
    v = make_visit(client, org_a, stage="consult")
    key = "rx-" + uuid.uuid4().hex
    headers = {**v.doctor, "Idempotency-Key": key}
    url = f"/api/v1/encounters/{v.enc_id}/prescriptions"
    first = client.post(url, headers=headers, json=rx_body("Paracetamol 500 mg"))
    again = client.post(url, headers=headers, json=rx_body("Paracetamol 500 mg"))
    assert first.status_code == 201 and again.status_code == 201, again.text
    assert again.json()["id"] == first.json()["id"]
    drafts = get(client, v.doctor, f"/patients/{v.patient['id']}/prescriptions").json()
    assert len(drafts) == 1

    # Without a key, or with a new one, a second prescription is a deliberate act and is allowed.
    other = client.post(
        url,
        headers={**v.doctor, "Idempotency-Key": "rx-" + uuid.uuid4().hex},
        json=rx_body("Cetirizine 10 mg"),
    )
    assert other.status_code == 201 and other.json()["id"] != first.json()["id"]


def test_a_refused_prescription_does_not_use_up_its_key(client: TestClient, org_a: H) -> None:
    v = make_visit(
        client, org_a, stage="triage"
    )  # consultation not started: prescribing is refused
    key = "rx-" + uuid.uuid4().hex
    url = f"/api/v1/encounters/{v.enc_id}/prescriptions"
    refused = client.post(
        url, headers={**v.doctor, "Idempotency-Key": key}, json=rx_body("Paracetamol 500 mg")
    )
    assert refused.status_code in (403, 409), refused.text
    r = post(client, v.doctor, "/encounters/consultation", {"appointment_id": v.appt_id})
    assert r.status_code == 200, r.text
    ok = client.post(
        url, headers={**v.doctor, "Idempotency-Key": key}, json=rx_body("Paracetamol 500 mg")
    )
    assert ok.status_code == 201, ok.text
