"""Long lists are read a page at a time, newest first, without skipping or repeating a row, and a
retried request for a new draft invoice returns the first draft."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.clinical_helpers import Visit, get, make_visit, post
from tests.conftest import make_staff

H = dict[str, str]
ORG = "alpha-clinic"


@pytest.fixture
def v(client: TestClient, org_a: H) -> Visit:
    return make_visit(client, org_a, stage="consult")


@pytest.fixture
def billing(client: TestClient, org_a: H) -> H:
    return make_staff(
        client, org_a, "bill@alpha-clinic.example.com", "billing_staff", "alpha-clinic"
    )[0]


def new_draft(client: TestClient, h: H, patient_id: str, key: str | None = None) -> Any:
    headers = {**h, "Idempotency-Key": key} if key else h
    return client.post("/api/v1/invoices", headers=headers, json={"patient_id": patient_id})


def pages(client: TestClient, h: H, url: str, size: int, **params: Any) -> list[list[str]]:
    out: list[list[str]] = []
    before: str | None = None
    while True:
        q = {**params, "limit": size, **({"before": before} if before else {})}
        page = [r["id"] for r in get(client, h, url, **q).json()]
        if page:
            out.append(page)
        if len(page) < size:
            return out
        before = page[-1]


def test_invoices_are_paged_newest_first_without_gaps_or_repeats(
    client: TestClient, v: Visit, billing: H
) -> None:
    made = [new_draft(client, billing, v.patient["id"]).json()["id"] for _ in range(7)]
    everything = [r["id"] for r in get(client, billing, "/invoices", limit=200).json()]
    assert everything[:7] == list(reversed(made))

    paged = pages(client, billing, "/invoices", 3)
    assert [len(p) for p in paged] == [3, 3, 1]
    flat = [i for p in paged for i in p]
    assert flat == everything and len(set(flat)) == len(flat)

    # Filters still apply on every page.
    drafts = pages(client, billing, "/invoices", 2, status="DRAFT")
    assert sorted(i for p in drafts for i in p) == sorted(made)


def test_an_unknown_page_marker_is_refused(client: TestClient, billing: H, org_a: H) -> None:
    r = get(client, billing, "/invoices", before=str(uuid.uuid4()))
    assert r.status_code == 400 and r.json()["title"] == "invalid_cursor"
    r = get(client, org_a, "/audit-logs", before=str(uuid.uuid4()))
    assert r.status_code == 400


def test_another_organisations_row_cannot_be_used_to_page(
    client: TestClient, v: Visit, billing: H, org_b: H
) -> None:
    mine = new_draft(client, billing, v.patient["id"]).json()["id"]
    r = get(client, org_b, "/audit-logs", before=mine)
    assert r.status_code == 400


def test_the_audit_log_is_paged_the_same_way(client: TestClient, org_a: H) -> None:
    for i in range(5):
        r = post(client, org_a, "/facilities", {"name": f"Wing {i}", "code": f"W{i}"})
        assert r.status_code == 201, r.text
    everything = [r["id"] for r in get(client, org_a, "/audit-logs", limit=200).json()]
    flat = [i for p in pages(client, org_a, "/audit-logs", 2) for i in p]
    assert flat == everything


def test_a_repeated_request_for_a_new_draft_returns_the_first(
    client: TestClient, v: Visit, billing: H
) -> None:
    key = "inv-" + uuid.uuid4().hex
    first = new_draft(client, billing, v.patient["id"], key)
    again = new_draft(client, billing, v.patient["id"], key)
    assert first.status_code == 201 and again.status_code == 201, again.text
    assert again.json()["id"] == first.json()["id"]
    drafts = get(client, billing, "/invoices", patient_id=v.patient["id"], status="DRAFT").json()
    assert len(drafts) == 1
    # A new key is a deliberate second draft.
    other = new_draft(client, billing, v.patient["id"], "inv-" + uuid.uuid4().hex)
    assert other.status_code == 201 and other.json()["id"] != first.json()["id"]


def test_clinical_lists_page_the_same_way(client: TestClient, org_a: H) -> None:
    from tests.clinical_helpers import rx_body

    visit = make_visit(client, org_a, stage="consult")
    lab = make_staff(client, org_a, "lab-page@alpha-clinic.example.com", "lab_technician", ORG)[0]
    placed = []
    for i in range(5):
        o = post(
            client,
            visit.doctor,
            f"/encounters/{visit.enc_id}/orders",
            {"category": "LAB", "name": f"Test {i}", "reason": "Review"},
        ).json()
        placed.append(post(client, visit.doctor, f"/orders/{o['id']}/place").json()["id"])
    for _ in range(5):
        r = post(
            client, lab, f"/orders/{placed[0]}/results", {"test_name": "Hb", "value_text": "ok"}
        )
        assert r.status_code == 201, r.text
    for i in range(3):
        r = post(
            client, visit.doctor, f"/encounters/{visit.enc_id}/prescriptions", rx_body(f"Drug {i}")
        )
        assert r.status_code == 201, r.text

    pid = visit.patient["id"]
    for who, url, expected in (
        (lab, "/orders", 5),
        (visit.doctor, f"/patients/{pid}/results", 5),
        (visit.doctor, f"/patients/{pid}/prescriptions", 3),
        (visit.doctor, f"/patients/{pid}/encounters", 1),
    ):
        everything = [r["id"] for r in get(client, who, url, limit=200).json()]
        assert len(everything) == expected, url
        assert [i for p in pages(client, who, url, 2) for i in p] == everything, url
