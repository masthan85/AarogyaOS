from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.modules.cover.service import today
from tests.clinical_helpers import Visit, get, make_visit, post
from tests.conftest import make_staff
from tests.helpers import make_practitioner

H = dict[str, str]


@pytest.fixture
def v(client: TestClient, org_a: H) -> Visit:
    return make_visit(client, org_a, stage="consult")


@pytest.fixture
def colleague(client: TestClient, org_a: H, v: Visit) -> tuple[H, dict[str, Any]]:
    h, prac = make_practitioner(client, org_a, "alpha-clinic", v.facility, "dr.iyer@x.example.com")
    return h, prac


@pytest.fixture
def lab(client: TestClient, org_a: H) -> H:
    return make_staff(
        client, org_a, "lab@alpha-clinic.example.com", "lab_technician", "alpha-clinic"
    )[0]


def window(days: int = 3) -> dict[str, str]:
    return {"starts_on": str(today()), "ends_on": str(today() + timedelta(days=days))}


def a_result(client: TestClient, v: Visit, lab: H) -> str:
    o = post(
        client, v.doctor, f"/encounters/{v.enc_id}/orders", {"category": "LAB", "name": "Potassium"}
    )
    order_id = o.json()["id"]
    assert post(client, v.doctor, f"/orders/{order_id}/place").status_code == 200
    r = post(
        client,
        lab,
        f"/orders/{order_id}/results",
        {
            "test_name": "K",
            "value_numeric": 2.0,
            "ref_low": 3.5,
            "ref_high": 5.0,
            "critical_low": 2.5,
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def test_cover_lets_a_colleague_review_and_the_review_is_attributed_to_them(
    client: TestClient, v: Visit, colleague: tuple[H, dict[str, Any]], lab: H
) -> None:
    other, prac = colleague
    result_id = a_result(client, v, lab)
    assert get(client, other, "/results/awaiting-review").json() == []

    r = post(client, v.doctor, "/cover", {"to_user_id": prac["user_id"], **window()})
    assert r.status_code == 201, r.text
    assert r.json()["active"] is True

    rows = get(client, other, "/results/awaiting-review").json()
    assert [x["id"] for x in rows] == [result_id]
    assert rows[0]["covering_for"] == "dr.rao"
    # The owner's own list is unchanged and shows no "covering" label.
    assert get(client, v.doctor, "/results/awaiting-review").json()[0]["covering_for"] is None

    assert post(client, other, f"/results/{result_id}/review").status_code == 200
    assert get(client, v.doctor, "/results/awaiting-review").json() == []
    audit = get(client, v.admin, "/audit-logs", action="RESULT_REVIEWED").json()
    assert audit and audit[0]["after"]["on_behalf_of"]


def test_cover_stops_when_ended_or_outside_its_dates(
    client: TestClient, v: Visit, colleague: tuple[H, dict[str, Any]], lab: H
) -> None:
    other, prac = colleague
    a_result(client, v, lab)
    future = {
        "starts_on": str(today() + timedelta(days=2)),
        "ends_on": str(today() + timedelta(days=4)),
    }
    c = post(client, v.doctor, "/cover", {"to_user_id": prac["user_id"], **future}).json()
    assert c["active"] is False
    assert get(client, other, "/results/awaiting-review").json() == []

    c = post(client, v.doctor, "/cover", {"to_user_id": prac["user_id"], **window()}).json()
    assert len(get(client, other, "/results/awaiting-review").json()) == 1
    # Either side can end it.
    assert post(client, other, f"/cover/{c['id']}/end").json()["active"] is False
    assert get(client, other, "/results/awaiting-review").json() == []


def test_cover_is_validated_and_limited_to_doctors(
    client: TestClient, v: Visit, colleague: tuple[H, dict[str, Any]], lab: H
) -> None:
    _, prac = colleague
    me = v.prac["user_id"]
    assert post(client, v.doctor, "/cover", {"to_user_id": me, **window()}).status_code == 409
    bad = {"starts_on": str(today()), "ends_on": str(today() - timedelta(days=1))}
    assert (
        post(client, v.doctor, "/cover", {"to_user_id": prac["user_id"], **bad}).status_code == 422
    )
    long = window(60)
    assert (
        post(client, v.doctor, "/cover", {"to_user_id": prac["user_id"], **long}).status_code == 422
    )
    nurse_id = get(client, v.admin, "/users").json()
    nurse = next(u for u in nurse_id if u["email"].startswith("nurse"))
    assert (
        post(client, v.doctor, "/cover", {"to_user_id": nurse["id"], **window()}).status_code == 404
    )
    # Lab staff and reception cannot use it at all.
    for h in (lab, v.recep, v.nurse):
        assert get(client, h, "/cover").status_code == 403


def test_cover_cannot_be_ended_by_a_third_party_or_seen_across_organisations(
    client: TestClient, v: Visit, colleague: tuple[H, dict[str, Any]], org_b: H
) -> None:
    _, prac = colleague
    c = post(client, v.doctor, "/cover", {"to_user_id": prac["user_id"], **window()}).json()
    third, _ = make_staff(client, v.admin, "dr.third@x.example.com", "doctor", "alpha-clinic")
    assert post(client, third, f"/cover/{c['id']}/end").status_code == 404
    assert get(client, third, "/cover").json() == []
    assert get(client, v.doctor, "/cover/colleagues").json()[0]["name"] == "dr.iyer"
    assert post(client, org_b, f"/cover/{c['id']}/end").status_code in (403, 404)
