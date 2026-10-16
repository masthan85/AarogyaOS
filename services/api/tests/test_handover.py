"""Handing an open consultation to a colleague."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.clinical_helpers import Visit, get, make_visit, post, rx_body
from tests.conftest import make_staff
from tests.helpers import make_facility, make_practitioner

H = dict[str, str]


@pytest.fixture
def v(client: TestClient, org_a: H) -> Visit:
    return make_visit(client, org_a, stage="consult")


@pytest.fixture
def colleague(client: TestClient, org_a: H, v: Visit) -> tuple[H, dict[str, Any]]:
    return make_practitioner(client, org_a, "alpha-clinic", v.facility, "dr.iyer@x.example.com")


def hand(client: TestClient, v: Visit, to: str) -> Any:
    return post(client, v.doctor, f"/encounters/{v.enc_id}/handover", {"to_practitioner_id": to})


def test_handover_moves_ownership_and_the_first_doctor_loses_write_access(
    client: TestClient, v: Visit, colleague: tuple[H, dict[str, Any]]
) -> None:
    other, prac = colleague
    note = {"note_type": "ASSESSMENT", "content": "Viral fever"}
    assert post(client, other, f"/encounters/{v.enc_id}/notes", note).status_code == 403
    r = hand(client, v, prac["id"])
    assert r.status_code == 200, r.text
    assert r.json()["practitioner_id"] == prac["id"]
    assert post(client, other, f"/encounters/{v.enc_id}/notes", note).status_code == 201
    assert post(client, v.doctor, f"/encounters/{v.enc_id}/notes", note).status_code == 403
    log = get(client, v.admin, "/audit-logs", action="ENCOUNTER_HANDED_OVER").json()
    assert len(log) == 1 and log[0]["after"]["practitioner_id"] == prac["id"]
    queue = get(client, other, "/queue", facility_id=v.facility["id"]).json()
    assert all(
        q["practitioner_id"] == prac["id"] for q in queue if q["patient_id"] == v.patient["id"]
    )


def test_unfinished_work_must_be_resolved_first(
    client: TestClient, v: Visit, colleague: tuple[H, dict[str, Any]]
) -> None:
    _, prac = colleague
    rx = post(client, v.doctor, f"/encounters/{v.enc_id}/prescriptions", rx_body("Paracetamol"))
    assert rx.status_code == 201, rx.text
    r = hand(client, v, prac["id"])
    assert r.status_code == 409 and "drafts" in r.text
    post(client, v.doctor, f"/prescriptions/{rx.json()['id']}/void", {"reason": "not needed"})
    order = post(
        client, v.doctor, f"/encounters/{v.enc_id}/orders", {"category": "LAB", "name": "CBC"}
    )
    assert hand(client, v, prac["id"]).status_code == 409
    post(client, v.doctor, f"/orders/{order.json()['id']}/cancel", {"reason": "not needed"})
    assert hand(client, v, prac["id"]).status_code == 200


def test_who_may_hand_over_and_to_whom(
    client: TestClient, org_a: H, v: Visit, colleague: tuple[H, dict[str, Any]]
) -> None:
    other, prac = colleague
    assert (
        post(
            client, other, f"/encounters/{v.enc_id}/handover", {"to_practitioner_id": prac["id"]}
        ).status_code
        == 403
    )
    assert (
        post(
            client, v.nurse, f"/encounters/{v.enc_id}/handover", {"to_practitioner_id": prac["id"]}
        ).status_code
        == 403
    )
    assert hand(client, v, v.prac["id"]).status_code == 404  # to yourself
    elsewhere = make_facility(client, org_a, code="SITE2")
    far, far_prac = make_practitioner(
        client, org_a, "alpha-clinic", elsewhere, "dr.far@x.example.com"
    )
    del far
    assert hand(client, v, far_prac["id"]).status_code == 409
    assert hand(client, v, "00000000-0000-0000-0000-000000000000").status_code == 404
    stranger, _ = make_staff(client, org_a, "dr.third@x.example.com", "doctor", "alpha-clinic")
    del stranger
