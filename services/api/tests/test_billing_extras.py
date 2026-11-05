from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

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
    assert post(client, visit.doctor, f"/encounters/{visit.enc_id}/complete").status_code == 200
    return visit


@pytest.fixture
def billing(client: TestClient, org_a: H) -> H:
    return make_staff(
        client, org_a, "bill@alpha-clinic.example.com", "billing_staff", "alpha-clinic"
    )[0]


def issued(client: TestClient, h: H, v: Visit, lines: list[dict[str, Any]] | None = None) -> Any:
    inv = post(client, h, "/invoices", {"patient_id": v.patient["id"]}).json()
    body = {"lines": lines or [{"description": "Consultation", "unit_price_paise": 50000}]}
    assert put(client, h, f"/invoices/{inv['id']}/lines", body).status_code == 200
    r = post(client, h, f"/invoices/{inv['id']}/issue")
    assert r.status_code == 200, r.text
    return r.json()


def pay(client: TestClient, h: H, inv: Any, amount: int, method: str = "CASH") -> Any:
    r = post(
        client, h, f"/invoices/{inv['id']}/payments", {"amount_paise": amount, "method": method}
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_tax_is_worked_out_per_line_and_frozen_with_the_gstin(
    client: TestClient, v: Visit, billing: H
) -> None:
    bad = put(client, billing, "/billing/settings", {"gstin": "NOT-A-GSTIN"})
    assert bad.status_code == 422
    ok = put(client, billing, "/billing/settings", {"gstin": "29abcde1234f1z5"})
    assert ok.status_code == 200 and ok.json()["gstin"] == "29ABCDE1234F1Z5"
    lines = [
        {"description": "Lab test", "quantity": 3, "unit_price_paise": 3333, "tax_rate_bp": 1800},
        {"description": "Consultation", "unit_price_paise": 50000},
    ]
    inv = issued(client, billing, v, lines)
    # 3 x 33.33 = 99.99; 18% = 17.9982 -> 18.00
    assert inv["lines"][0]["tax_paise"] == 1800 and inv["tax_paise"] == 1800
    assert inv["total_paise"] == 9999 + 50000 + 1800
    assert inv["seller_gstin"] == "29ABCDE1234F1Z5"
    put(client, billing, "/billing/settings", {"gstin": None})
    assert (
        get(client, billing, f"/invoices/{inv['id']}").json()["seller_gstin"] == "29ABCDE1234F1Z5"
    )


def test_tax_rate_is_limited(client: TestClient, v: Visit, billing: H) -> None:
    inv = post(client, billing, "/invoices", {"patient_id": v.patient["id"]}).json()
    r = put(
        client, billing, f"/invoices/{inv['id']}/lines",
        {"lines": [{"description": "Thing", "unit_price_paise": 100, "tax_rate_bp": 5000}]},
    )  # fmt: skip
    assert r.status_code == 422


def test_credit_note_then_refund_of_the_overpayment(
    client: TestClient, v: Visit, billing: H
) -> None:
    inv = issued(client, billing, v)
    pay(client, billing, inv, 50000, "UPI")
    too_soon = post(
        client, billing, f"/invoices/{inv['id']}/refunds",
        {"amount_paise": 100, "method": "UPI", "reason": "Wrong charge"},
    )  # fmt: skip
    assert too_soon.status_code == 409  # nothing paid beyond what is owed yet
    cn = post(
        client, billing, f"/invoices/{inv['id']}/credit-notes",
        {"amount_paise": 20000, "reason": "Discount agreed after the visit"},
    )  # fmt: skip
    assert cn.status_code == 201, cn.text
    body = cn.json()
    assert body["credit_notes"][0]["number"] == "CN-000001"
    assert body["net_paise"] == 30000 and body["balance_paise"] == 0
    assert body["refund_due_paise"] == 20000
    over = post(
        client, billing, f"/invoices/{inv['id']}/refunds",
        {"amount_paise": 20001, "method": "UPI", "reason": "Refund"},
    )  # fmt: skip
    assert over.status_code == 409
    ok = post(
        client, billing, f"/invoices/{inv['id']}/refunds",
        {"amount_paise": 20000, "method": "UPI", "reason": "Discount refund", "reference": "R1"},
    ).json()  # fmt: skip
    assert ok["refund_due_paise"] == 0 and ok["refunded_paise"] == 20000
    assert ok["balance_paise"] == 0


def test_credit_cannot_exceed_value_and_a_paid_invoice_cannot_be_voided(
    client: TestClient, v: Visit, billing: H
) -> None:
    inv = issued(client, billing, v)
    big = post(
        client, billing, f"/invoices/{inv['id']}/credit-notes",
        {"amount_paise": 50001, "reason": "Too much"},
    )  # fmt: skip
    assert big.status_code == 409
    pay(client, billing, inv, 10000)
    void = post(client, billing, f"/invoices/{inv['id']}/void", {"reason": "Mistake made"})
    assert void.status_code == 409 and "credit note" in void.json()["detail"].lower()
    full = post(
        client, billing, f"/invoices/{inv['id']}/credit-notes",
        {"amount_paise": 50000, "reason": "Cancelled visit"},
    ).json()  # fmt: skip
    assert full["net_paise"] == 0 and full["refund_due_paise"] == 10000


def test_receptionists_cannot_adjust_or_change_prices(
    client: TestClient, v: Visit, billing: H
) -> None:
    inv = issued(client, billing, v)
    pay(client, billing, inv, 50000)
    for url, body in (
        (f"/invoices/{inv['id']}/credit-notes", {"amount_paise": 100, "reason": "Test only"}),
        (
            f"/invoices/{inv['id']}/refunds",
            {"amount_paise": 100, "method": "CASH", "reason": "Test"},
        ),
        (f"/invoices/{inv['id']}/claims", {"insurer": "Acme", "claimed_paise": 100}),
        ("/billing/prices", {"name": "X-ray", "price_paise": 100}),
    ):
        assert post(client, v.recep, url, body).status_code == 403
    assert get(client, v.recep, "/billing/prices").status_code == 200


def test_price_list_is_unique_and_does_not_change_old_invoices(
    client: TestClient, v: Visit, billing: H
) -> None:
    p = post(client, billing, "/billing/prices", {"name": "X-ray chest", "price_paise": 40000})
    assert p.status_code == 201, p.text
    assert (
        post(
            client, billing, "/billing/prices", {"name": "x-ray CHEST", "price_paise": 1}
        ).status_code
        == 409
    )
    inv = issued(client, billing, v, [{"description": "X-ray chest", "unit_price_paise": 40000}])
    put(client, billing, f"/billing/prices/{p.json()['id']}", {"price_paise": 45000})
    assert get(client, billing, f"/invoices/{inv['id']}").json()["total_paise"] == 40000
    put(client, billing, f"/billing/prices/{p.json()['id']}", {"active": False})
    assert get(client, billing, "/billing/prices").json() == []
    assert len(get(client, billing, "/billing/prices", all="true").json()) == 1


def test_end_of_day_totals_and_one_closing_per_day(
    client: TestClient, v: Visit, billing: H
) -> None:
    inv = issued(client, billing, v)
    pay(client, billing, inv, 30000, "CASH")
    pay(client, billing, inv, 20000, "UPI")
    cn = post(
        client,
        billing,
        f"/invoices/{inv['id']}/credit-notes",
        {"amount_paise": 5000, "reason": "Rebate"},
    )
    assert cn.status_code == 201
    post(
        client, billing, f"/invoices/{inv['id']}/refunds",
        {"amount_paise": 5000, "method": "CASH", "reason": "Rebate"},
    )  # fmt: skip
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    s = get(client, billing, "/billing/day", on=today).json()
    cash = next(m for m in s["by_method"] if m["method"] == "CASH")
    assert cash["net_paise"] == 25000 and s["expected_cash_paise"] == 25000
    assert s["net_paise"] == 45000
    closed = post(
        client, billing, "/billing/day/close", {"business_date": today, "counted_cash_paise": 24000}
    )
    assert closed.status_code == 201, closed.text
    assert closed.json()["closing"]["difference_paise"] == -1000
    assert (
        post(
            client,
            billing,
            "/billing/day/close",
            {"business_date": today, "counted_cash_paise": 25000},
        ).status_code
        == 409
    )
    future = post(
        client,
        billing,
        "/billing/day/close",
        {"business_date": "2999-01-01", "counted_cash_paise": 0},
    )
    assert future.status_code == 409


def test_claims_are_tracked_and_bounded(client: TestClient, v: Visit, billing: H) -> None:
    inv = issued(client, billing, v)
    c = post(
        client,
        billing,
        f"/invoices/{inv['id']}/claims",
        {"insurer": "Star Health", "claimed_paise": 40000},
    )
    assert c.status_code == 201, c.text
    too_much = post(
        client,
        billing,
        f"/invoices/{inv['id']}/claims",
        {"insurer": "Other", "claimed_paise": 20000},
    )
    assert too_much.status_code == 409
    no_amount = put(client, billing, f"/claims/{c.json()['id']}", {"status": "APPROVED"})
    assert no_amount.status_code == 409
    ok = put(
        client,
        billing,
        f"/claims/{c.json()['id']}",
        {"status": "PART_APPROVED", "approved_paise": 30000},
    )
    assert ok.status_code == 200 and ok.json()["approved_paise"] == 30000
    settled = put(client, billing, f"/claims/{c.json()['id']}", {"status": "SETTLED"})
    assert settled.status_code == 200
    assert put(client, billing, f"/claims/{c.json()['id']}", {"note": "x"}).status_code == 409
    assert pay(client, billing, inv, 30000, "INSURER")["paid_paise"] == 30000
    assert len(get(client, billing, f"/invoices/{inv['id']}/claims").json()) == 1


def test_adjustment_records_cannot_be_rewritten(
    client: TestClient, v: Visit, billing: H, db: Session
) -> None:
    inv = issued(client, billing, v)
    post(
        client,
        billing,
        f"/invoices/{inv['id']}/credit-notes",
        {"amount_paise": 100, "reason": "Rounding"},
    )
    set_tenant(db, None, bypass=True)
    for sql in (
        "update credit_notes set amount_paise = 1",
        "delete from credit_notes",
    ):
        with pytest.raises(DBAPIError):
            db.execute(text(sql))
        db.rollback()
        set_tenant(db, None, bypass=True)
