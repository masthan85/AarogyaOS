from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.db import set_tenant
from tests.clinical_helpers import Visit, get, make_visit, post, record_nka
from tests.conftest import make_staff

H = dict[str, str]


def put(client: TestClient, h: H, url: str, body: dict[str, Any]) -> Any:
    return client.put(f"/api/v1{url}", headers=h, json=body)


@pytest.fixture
def v(client: TestClient, org_a: H) -> Visit:
    visit = make_visit(client, org_a, stage="consult")
    record_nka(client, visit)
    done = post(client, visit.doctor, f"/encounters/{visit.enc_id}/complete")
    assert done.status_code == 200, done.text
    return visit


@pytest.fixture
def billing(client: TestClient, org_a: H) -> H:
    return make_staff(
        client, org_a, "bill@alpha-clinic.example.com", "billing_staff", "alpha-clinic"
    )[0]


def draft(client: TestClient, h: H, v: Visit, **kw: Any) -> dict[str, Any]:
    r = post(
        client, h, "/invoices", {"patient_id": v.patient["id"], "encounter_id": v.enc_id, **kw}
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


LINES = {
    "lines": [
        {"description": "Consultation", "quantity": 1, "unit_price_paise": 50000},
        {"description": "Dressing", "quantity": 2, "unit_price_paise": 7500},
    ]
}


def issued(client: TestClient, h: H, v: Visit) -> dict[str, Any]:
    inv = draft(client, h, v)
    assert put(client, h, f"/invoices/{inv['id']}/lines", LINES).status_code == 200
    r = post(client, h, f"/invoices/{inv['id']}/issue")
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_a_visit_is_billed_from_draft_to_paid_and_the_totals_add_up(
    client: TestClient, v: Visit, billing: H
) -> None:
    inv = draft(client, billing, v)
    assert inv["status"] == "DRAFT" and inv["number"] is None
    r = put(client, billing, f"/invoices/{inv['id']}/lines", LINES).json()
    assert r["total_paise"] == 65000 and r["balance_paise"] == 65000
    done = post(client, billing, f"/invoices/{inv['id']}/issue").json()
    assert done["number"] == "INV-000001" and done["status"] == "ISSUED"
    part = post(
        client,
        billing,
        f"/invoices/{inv['id']}/payments",
        {"amount_paise": 20000, "method": "UPI", "reference": "UPI123"},
    )
    assert part.status_code == 201 and part.json()["balance_paise"] == 45000
    over = post(
        client,
        billing,
        f"/invoices/{inv['id']}/payments",
        {"amount_paise": 45001, "method": "CASH"},
    )
    assert over.status_code == 409
    final = post(
        client,
        billing,
        f"/invoices/{inv['id']}/payments",
        {"amount_paise": 45000, "method": "CASH"},
    ).json()
    assert (
        final["balance_paise"] == 0 and final["paid_paise"] == 65000 and len(final["payments"]) == 2
    )
    unpaid = get(client, billing, "/invoices", unpaid="true").json()
    assert unpaid == []


def test_numbers_run_on_and_an_issued_invoice_cannot_be_edited(
    client: TestClient, v: Visit, billing: H
) -> None:
    first = issued(client, billing, v)
    second = post(client, billing, "/invoices", {"patient_id": v.patient["id"]}).json()
    put(client, billing, f"/invoices/{second['id']}/lines", LINES)
    assert post(client, billing, f"/invoices/{second['id']}/issue").json()["number"] == "INV-000002"
    assert put(client, billing, f"/invoices/{first['id']}/lines", LINES).status_code == 409
    assert post(client, billing, f"/invoices/{first['id']}/issue").status_code == 409


def test_the_database_itself_freezes_issued_invoices_and_payments(
    client: TestClient, v: Visit, billing: H, db: Session
) -> None:
    inv = issued(client, billing, v)
    post(
        client, billing, f"/invoices/{inv['id']}/payments", {"amount_paise": 1000, "method": "CASH"}
    )
    set_tenant(db, None, bypass=True)
    attempts = [
        ("update invoice_lines set unit_price_paise = 1", "cannot be changed"),
        ("delete from invoice_lines", "cannot be changed"),
        ("update invoices set total_paise = 1", "frozen"),
        ("delete from invoices", "cannot be deleted"),
        ("update payments set amount_paise = 1", "append-only"),
        ("delete from payments", "append-only"),
    ]
    for sql, message in attempts:
        with pytest.raises(DBAPIError, match=message):
            db.execute(text(sql))
        db.rollback()
        set_tenant(db, None, bypass=True)


def test_bad_charges_are_refused_and_an_empty_invoice_cannot_be_issued(
    client: TestClient, v: Visit, billing: H
) -> None:
    inv = draft(client, billing, v)
    url = f"/invoices/{inv['id']}/lines"
    bad = [
        {"description": "x", "quantity": 1, "unit_price_paise": 100},
        {"description": "Consultation", "quantity": 0, "unit_price_paise": 100},
        {"description": "Consultation", "quantity": 1, "unit_price_paise": -1},
    ]
    for line in bad:
        assert put(client, billing, url, {"lines": [line]}).status_code == 422
    assert post(client, billing, f"/invoices/{inv['id']}/issue").status_code == 409
    zero = {"lines": [{"description": "Waived", "quantity": 1, "unit_price_paise": 0}]}
    put(client, billing, url, zero)
    assert post(client, billing, f"/invoices/{inv['id']}/issue").status_code == 409


def test_who_may_see_and_change_billing(client: TestClient, org_a: H, v: Visit, billing: H) -> None:
    inv = issued(client, billing, v)
    for h in (v.doctor, v.nurse):
        assert get(client, h, "/invoices").status_code == 403
    assert get(client, v.recep, f"/invoices/{inv['id']}").status_code == 200
    assert (
        post(
            client,
            v.recep,
            f"/invoices/{inv['id']}/payments",
            {"amount_paise": 100, "method": "CASH"},
        ).status_code
        == 201
    )
    # An administrator can look but not change.
    assert get(client, org_a, "/invoices").status_code == 200
    assert post(client, org_a, "/invoices", {"patient_id": v.patient["id"]}).status_code == 403
    # Billing staff see charges, never the clinical record.
    assert get(client, billing, f"/patients/{v.patient['id']}/clinical-state").status_code == 403
    assert get(client, billing, f"/encounters/{v.enc_id}").status_code == 403


def test_visits_waiting_to_be_billed_and_the_void_rules(
    client: TestClient, v: Visit, billing: H
) -> None:
    waiting = get(client, billing, "/billing/to-bill").json()
    assert [w["encounter_id"] for w in waiting] == [v.enc_id]
    inv = issued(client, billing, v)
    assert get(client, billing, "/billing/to-bill").json() == []
    assert (
        post(
            client, billing, "/invoices", {"patient_id": v.patient["id"], "encounter_id": v.enc_id}
        ).status_code
        == 409
    )
    # Voiding an unpaid issued invoice puts the visit back, and keeps the invoice as void.
    voided = post(
        client, billing, f"/invoices/{inv['id']}/void", {"reason": "Wrong patient charged"}
    )
    assert (
        voided.status_code == 200
        and voided.json()["status"] == "VOID"
        and voided.json()["balance_paise"] == 0
    )
    assert [w["encounter_id"] for w in get(client, billing, "/billing/to-bill").json()] == [
        v.enc_id
    ]
    again = issued(client, billing, v)
    assert again["number"] == "INV-000002"
    post(
        client,
        billing,
        f"/invoices/{again['id']}/payments",
        {"amount_paise": 100, "method": "CASH"},
    )
    refused = post(client, billing, f"/invoices/{again['id']}/void", {"reason": "Changed my mind"})
    assert refused.status_code == 409 and "Refunds" in refused.text


def test_a_draft_can_be_discarded_and_other_organisations_cannot_see_invoices(
    client: TestClient, v: Visit, billing: H, org_b: H
) -> None:
    inv = draft(client, billing, v)
    assert get(client, org_b, f"/invoices/{inv['id']}").status_code in (403, 404)
    gone = post(client, billing, f"/invoices/{inv['id']}/void", {"reason": "Not needed"})
    assert gone.status_code == 200 and gone.json() is None
    assert get(client, billing, f"/invoices/{inv['id']}").status_code == 404
