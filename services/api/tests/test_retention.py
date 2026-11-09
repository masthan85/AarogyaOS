from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.db import set_tenant
from tests.clinical_helpers import Visit, get, make_visit, post, rx_body

H = dict[str, str]


@pytest.fixture
def v(client: TestClient, org_a: H) -> Visit:
    return make_visit(client, org_a, stage="consult")


def signed_rx(client: TestClient, v: Visit) -> dict[str, Any]:
    rx = post(
        client, v.doctor, f"/encounters/{v.enc_id}/prescriptions", rx_body("Paracetamol 500 mg")
    ).json()
    warns = post(client, v.doctor, f"/prescriptions/{rx['id']}/safety-check").json()["warnings"]
    done = post(
        client, v.doctor, f"/prescriptions/{rx['id']}/sign",
        {"acknowledged_warning_codes": [w["code"] for w in warns]},
    )  # fmt: skip
    assert done.status_code == 200, done.text
    return dict(done.json())


def test_a_signed_prescription_is_sealed_and_a_change_behind_the_apps_back_shows(
    client: TestClient, v: Visit, db: Session
) -> None:
    rx = signed_rx(client, v)
    ok = get(client, v.doctor, f"/prescriptions/{rx['id']}/integrity").json()
    assert ok["sealed"] is True and ok["intact"] is True
    set_tenant(db, None, bypass=True)
    # Someone with direct database access switches the guard off and edits the dose.
    db.execute(text("alter table prescription_items disable trigger prescription_items_guard"))
    db.execute(
        text("update prescription_items set dose = '10 tablets' where prescription_id = :i"),
        {"i": rx["id"]},
    )
    db.execute(text("alter table prescription_items enable trigger prescription_items_guard"))
    db.commit()
    bad = get(client, v.doctor, f"/prescriptions/{rx['id']}/integrity").json()
    assert bad["sealed"] is True and bad["intact"] is False
    assert "DOES NOT MATCH" in bad["message"]


def test_drafts_are_not_sealed(client: TestClient, v: Visit) -> None:
    rx = post(
        client, v.doctor, f"/encounters/{v.enc_id}/prescriptions", rx_body("Paracetamol 500 mg")
    ).json()
    r = get(client, v.doctor, f"/prescriptions/{rx['id']}/integrity").json()
    assert r == {"sealed": False, "intact": None, "message": "Drafts are not sealed."}


def test_legal_holds_are_admin_only_recorded_and_released_once(
    client: TestClient, v: Visit, db: Session
) -> None:
    url = f"/patients/{v.patient['id']}/legal-holds"
    for who in (v.doctor, v.nurse, v.recep):
        assert post(client, who, url, {"reason": "Court notice 12/2026"}).status_code == 403
    assert post(client, v.admin, url, {"reason": "no"}).status_code == 422
    hold = post(client, v.admin, url, {"reason": "Court notice 12/2026"})
    assert hold.status_code == 201, hold.text
    hid = hold.json()["id"]
    assert [h["id"] for h in get(client, v.admin, "/legal-holds").json()] == [hid]
    assert get(client, v.doctor, "/legal-holds").status_code == 403
    assert (
        post(client, v.doctor, f"/legal-holds/{hid}/release", {"reason": "Closed now"}).status_code
        == 403
    )
    rel = post(client, v.admin, f"/legal-holds/{hid}/release", {"reason": "Matter closed"})
    assert rel.status_code == 200 and rel.json()["released_at"]
    assert (
        post(client, v.admin, f"/legal-holds/{hid}/release", {"reason": "Again please"}).status_code
        == 409
    )
    assert get(client, v.admin, "/legal-holds").json() == []
    assert len(get(client, v.admin, "/legal-holds", all="true").json()) == 1
    audit = get(client, v.admin, "/audit-logs", action="LEGAL_HOLD_PLACED").json()
    assert audit and audit[0]["reason"] == "Court notice 12/2026"
    set_tenant(db, None, bypass=True)
    for sql in ("delete from legal_holds", "update legal_holds set reason = 'edited'"):
        with pytest.raises(DBAPIError):
            db.execute(text(sql))
        db.rollback()
        set_tenant(db, None, bypass=True)


def test_holds_are_private_to_the_organisation(client: TestClient, v: Visit, org_b: H) -> None:
    post(
        client,
        v.admin,
        f"/patients/{v.patient['id']}/legal-holds",
        {"reason": "Court notice 12/2026"},
    )
    assert get(client, org_b, "/legal-holds").json() == []


def test_a_dedicated_seal_key_survives_field_key_rotation(
    client: TestClient, v: Visit, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings
    from app.modules.clinical import seal

    rx = signed_rx(client, v)  # sealed with the key derived from the field key
    settings = get_settings()
    monkeypatch.setattr(settings, "seal_keys", "c2VhbC1rZXktb25lLTMyLWJ5dGVzLXh4eHh4eHh4eHg=")
    assert seal._keys()[0] != seal._keys()[-1]
    # Old seal still verifies because derived keys remain accepted...
    assert get(client, v.doctor, f"/prescriptions/{rx['id']}/integrity").json()["intact"] is True
    # ...and a new prescription is signed with the dedicated key and verifies too.
    second = signed_rx(client, v)
    assert (
        get(client, v.doctor, f"/prescriptions/{second['id']}/integrity").json()["intact"] is True
    )
    # Rotate the field key without listing the old one: the dedicated-key seal still holds,
    # the legacy one no longer does.
    monkeypatch.setattr(
        settings, "field_encryption_key", "b3RoZXIta2V5LXRoYXQtaXMtMzItYnl0ZXMteHh4eHg="
    )
    assert (
        get(client, v.doctor, f"/prescriptions/{second['id']}/integrity").json()["intact"] is True
    )
    assert get(client, v.doctor, f"/prescriptions/{rx['id']}/integrity").json()["intact"] is False
