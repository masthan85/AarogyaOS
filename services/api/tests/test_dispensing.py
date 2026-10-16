from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.db import set_tenant
from tests.clinical_helpers import Visit, get, make_visit, post, record_nka, rx_body
from tests.conftest import make_staff

H = dict[str, str]


@pytest.fixture
def v(client: TestClient, org_a: H) -> Visit:
    return make_visit(client, org_a, stage="consult")


@pytest.fixture
def pharmacist(client: TestClient, org_a: H) -> H:
    return make_staff(client, org_a, "ph@alpha-clinic.example.com", "pharmacist", "alpha-clinic")[0]


def signed(client: TestClient, v: Visit) -> dict[str, Any]:
    # An allergy status must be on record before a prescription can be signed.
    record_nka(client, v)
    rx = post(client, v.doctor, f"/encounters/{v.enc_id}/prescriptions", rx_body("Paracetamol"))
    assert rx.status_code == 201, rx.text
    s = post(client, v.doctor, f"/prescriptions/{rx.json()['id']}/sign")
    assert s.status_code == 200, s.text
    return dict(s.json())


def test_a_pharmacist_records_dispensing_and_it_is_visible_with_history(
    client: TestClient, v: Visit, pharmacist: H
) -> None:
    rx = signed(client, v)
    url = f"/prescriptions/{rx['id']}/dispensing"
    first = post(
        client,
        pharmacist,
        url,
        {"status": "PARTIALLY_DISPENSED", "note": "Out of stock: 3 days given"},
    )
    assert first.status_code == 201, first.text
    assert first.json()["dispensed_by_name"] == "ph"
    assert post(client, pharmacist, url, {"status": "DISPENSED"}).status_code == 201
    # Finished: a further record would only confuse the history.
    assert post(client, pharmacist, url, {"status": "NOT_DISPENSED"}).status_code == 409
    rows = get(client, v.doctor, f"/patients/{v.patient['id']}/dispensings").json()
    assert [r["status"] for r in rows] == ["DISPENSED", "PARTIALLY_DISPENSED"]
    log = get(client, v.admin, "/audit-logs", action="PRESCRIPTION_DISPENSED").json()
    assert len(log) == 1 and "stock" not in str(log)


def test_only_signed_prescriptions_and_only_pharmacists(
    client: TestClient, v: Visit, pharmacist: H
) -> None:
    rx = signed(client, v)
    url = f"/prescriptions/{rx['id']}/dispensing"
    for h in (v.doctor, v.nurse, v.recep, v.admin):
        assert post(client, h, url, {"status": "DISPENSED"}).status_code == 403
    assert post(client, pharmacist, url, {"status": "SOMETHING"}).status_code == 422
    draft = post(client, v.doctor, f"/encounters/{v.enc_id}/prescriptions", rx_body("Cetirizine"))
    assert (
        post(
            client,
            pharmacist,
            f"/prescriptions/{draft.json()['id']}/dispensing",
            {"status": "DISPENSED"},
        ).status_code
        == 404
    )
    post(client, v.doctor, f"/prescriptions/{rx['id']}/void", {"reason": "wrong patient"})
    r = post(client, pharmacist, url, {"status": "DISPENSED"})
    assert r.status_code == 409 and "voided" in r.text


def test_dispensing_records_cannot_be_changed_with_sql(
    client: TestClient, v: Visit, pharmacist: H, db: Session
) -> None:
    rx = signed(client, v)
    post(client, pharmacist, f"/prescriptions/{rx['id']}/dispensing", {"status": "DISPENSED"})
    set_tenant(db, None, bypass=True)
    for sql in ("update dispensings set status = 'NOT_DISPENSED'", "delete from dispensings"):
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(text(sql))
        db.rollback()
        set_tenant(db, None, bypass=True)
