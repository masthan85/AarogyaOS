from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import set_tenant
from tests.clinical_helpers import API, Visit, get, make_visit, post, record_nka, rx_body
from tests.conftest import make_staff

H = dict[str, str]


@pytest.fixture
def v(client: TestClient, org_a: H) -> Visit:
    return make_visit(client, org_a, stage="consult")


def draft(client: TestClient, v: Visit, *names: str) -> dict[str, Any]:
    r = post(client, v.doctor, f"/encounters/{v.enc_id}/prescriptions", rx_body(*names))
    assert r.status_code == 201, r.text
    return r.json()


def warning_codes(client: TestClient, v: Visit, rx_id: str) -> list[str]:
    r = post(client, v.doctor, f"/prescriptions/{rx_id}/safety-check")
    assert r.status_code == 200, r.text
    return [w["code"] for w in r.json()["warnings"]]


def test_only_the_treating_doctor_drafts_and_only_during_consultation(
    client: TestClient, v: Visit, org_a: H
) -> None:
    url = f"/encounters/{v.enc_id}/prescriptions"
    for h in (v.nurse, v.recep, v.admin):
        assert post(client, h, url, rx_body("Paracetamol")).status_code == 403
    from tests.helpers import make_practitioner

    other, _ = make_practitioner(
        client, org_a, "alpha-clinic", v.facility, "dr.other@x.example.com"
    )
    assert post(client, other, url, rx_body("Paracetamol")).status_code == 403


def test_cannot_prescribe_before_the_consultation_starts(client: TestClient, org_a: H) -> None:
    v = make_visit(client, org_a)  # triage only
    r = post(client, v.doctor, f"/encounters/{v.enc_id}/prescriptions", rx_body("Paracetamol"))
    # The booked doctor owns the encounter already, but the consultation has not started.
    assert r.status_code == 409


def test_item_validation(client: TestClient, v: Visit) -> None:
    url = f"/encounters/{v.enc_id}/prescriptions"
    assert post(client, v.doctor, url, {"items": []}).status_code == 422
    assert post(client, v.doctor, url, rx_body("Paracetamol", route="MOUTH")).status_code == 422
    bad = rx_body("Paracetamol")
    bad["items"][0]["duration_days"] = 0
    assert post(client, v.doctor, url, bad).status_code == 422


def test_unknown_allergy_status_blocks_signing_until_acknowledged(
    client: TestClient, v: Visit
) -> None:
    rx = draft(client, v, "Paracetamol 500 mg")
    refused = post(client, v.doctor, f"/prescriptions/{rx['id']}/sign")
    assert (
        refused.status_code == 409 and refused.json()["title"] == "warnings_require_acknowledgement"
    )
    assert [w["code"] for w in refused.json()["warnings"]] == ["ALLERGY_STATUS_UNKNOWN"]
    signed = post(
        client,
        v.doctor,
        f"/prescriptions/{rx['id']}/sign",
        {"acknowledged_warning_codes": ["ALLERGY_STATUS_UNKNOWN"]},
    )
    assert signed.status_code == 200 and signed.json()["status"] == "SIGNED"
    snap = signed.json()["safety_snapshot"]
    assert snap["acknowledged"] == ["ALLERGY_STATUS_UNKNOWN"]
    assert "Drug-drug interactions" in snap["checks_not_performed"]


def test_checks_limited_notice_is_always_present_and_never_blocks(
    client: TestClient, v: Visit
) -> None:
    record_nka(client, v)
    rx = draft(client, v, "Paracetamol 500 mg")
    r = post(client, v.doctor, f"/prescriptions/{rx['id']}/safety-check").json()
    assert [w["code"] for w in r["warnings"]] == ["CHECKS_LIMITED"] and r["warnings"][0][
        "level"
    ] == "INFO"
    assert "NOT checked" in r["warnings"][0]["message"]
    assert post(client, v.doctor, f"/prescriptions/{rx['id']}/sign").status_code == 200


def test_unverified_possible_allergy_still_triggers_a_name_match_warning(
    client: TestClient, v: Visit
) -> None:
    post(
        client,
        v.nurse,
        f"/encounters/{v.enc_id}/allergies",
        {"substance": "Penicillin", "certainty": "POSSIBLE", "source": "PATIENT_REPORTED"},
    )
    rx = draft(client, v, "Penicillin V 250 mg", "Paracetamol 500 mg")
    codes = warning_codes(client, v, rx["id"])
    match = [c for c in codes if c.startswith("ALLERGY_MATCH:1:")]
    assert len(match) == 1 and not any(c.startswith("ALLERGY_MATCH:2") for c in codes)
    r = post(client, v.doctor, f"/prescriptions/{rx['id']}/safety-check").json()
    assert "unverified possible allergy to Penicillin" in next(
        w["message"] for w in r["warnings"] if w["code"] == match[0]
    )
    # Must acknowledge the specific warning, not just anything.
    assert (
        post(
            client,
            v.doctor,
            f"/prescriptions/{rx['id']}/sign",
            {"acknowledged_warning_codes": ["SOMETHING_ELSE"]},
        ).status_code
        == 409
    )
    assert (
        post(
            client,
            v.doctor,
            f"/prescriptions/{rx['id']}/sign",
            {"acknowledged_warning_codes": match},
        ).status_code
        == 200
    )


def test_name_matching_does_not_pretend_to_know_drug_classes(client: TestClient, v: Visit) -> None:
    """Amoxicillin is a penicillin, but without a drug database we cannot know that. The system
    must not claim it did; the limitation notice carries the message instead."""
    post(
        client,
        v.doctor,
        f"/encounters/{v.enc_id}/allergies",
        {"substance": "Penicillin", "severity": "SEVERE"},
    )
    rx = draft(client, v, "Amoxicillin 500 mg")
    r = post(client, v.doctor, f"/prescriptions/{rx['id']}/safety-check").json()
    assert not any(w["code"].startswith("ALLERGY_MATCH") for w in r["warnings"])
    assert any("cross-sensitivity" in n for n in r["checks_not_performed"])


def test_duplicates_within_prescription_and_with_current_medicines(
    client: TestClient, v: Visit
) -> None:
    record_nka(client, v)
    post(
        client,
        v.nurse,
        f"/encounters/{v.enc_id}/medications",
        {"name": "Metformin 500 mg", "generic_name": "metformin"},
    )
    r = post(client, v.doctor, f"/encounters/{v.enc_id}/prescriptions", {"items": [
        {"medicine_name": "Metformin 850 mg", "generic_name": "metformin", "dose": "1", "route": "ORAL", "frequency": "BD"},
        {"medicine_name": "Paracetamol 500 mg", "dose": "1", "route": "ORAL", "frequency": "SOS"},
        {"medicine_name": "Paracetamol 650 mg", "dose": "1", "route": "ORAL", "frequency": "SOS"},
    ]})  # fmt: skip
    codes = warning_codes(client, v, r.json()["id"])
    assert any(c.startswith("DUPLICATE_THERAPY:1:") for c in codes)
    assert "DUPLICATE_IN_PRESCRIPTION:2:3" in codes


def test_signed_prescriptions_are_immutable_everywhere(
    client: TestClient, v: Visit, superuser_engine: Any
) -> None:
    record_nka(client, v)
    rx = draft(client, v, "Paracetamol 500 mg")
    assert post(client, v.doctor, f"/prescriptions/{rx['id']}/sign").status_code == 200
    # API layer
    assert (
        client.put(
            f"{API}/prescriptions/{rx['id']}", headers=v.doctor, json=rx_body("Ibuprofen")
        ).status_code
        == 409
    )
    assert post(client, v.doctor, f"/prescriptions/{rx['id']}/sign").status_code == 409
    # Database layer: even raw SQL cannot change a signed prescription or its items.
    maker = client.app.state.sessionmaker  # type: ignore[attr-defined]
    for sql in (
        "update prescription_items set dose = '10 tablets'",
        "delete from prescription_items",
        "insert into prescription_items (id, organisation_id, prescription_id, position, medicine_name, dose, route, frequency) "
        "select gen_random_uuid(), organisation_id, prescription_id, 9, 'X', '1', 'ORAL', 'od' from prescription_items",
        "update prescriptions set notes = 'tampered'",
        "update prescriptions set status = 'DRAFT'",
        "delete from prescriptions",
    ):
        with maker() as s:
            set_tenant(s, None, bypass=True)
            with pytest.raises(DBAPIError):
                s.execute(text(sql))
                s.commit()


def test_voiding_keeps_the_record_and_allows_a_replacement(client: TestClient, v: Visit) -> None:
    record_nka(client, v)
    rx = draft(client, v, "Paracetamol 500 mg")
    post(client, v.doctor, f"/prescriptions/{rx['id']}/sign")
    assert (
        post(client, v.doctor, f"/prescriptions/{rx['id']}/void", {"reason": "x"}).status_code
        == 422
    )
    voided = post(
        client, v.doctor, f"/prescriptions/{rx['id']}/void", {"reason": "Wrong dose written"}
    )
    assert (
        voided.status_code == 200 and voided.json()["status"] == "VOIDED" and voided.json()["items"]
    )
    assert (
        post(client, v.doctor, f"/prescriptions/{rx['id']}/void", {"reason": "again"}).status_code
        == 409
    )
    assert (
        client.put(
            f"{API}/prescriptions/{rx['id']}", headers=v.doctor, json=rx_body("Ibuprofen")
        ).status_code
        == 409
    )
    replacement = draft(client, v, "Paracetamol 650 mg")
    assert post(client, v.doctor, f"/prescriptions/{replacement['id']}/sign").status_code == 200
    assert post(client, v.doctor, f"/encounters/{v.enc_id}/complete").status_code == 200


def test_editing_a_draft_replaces_items_and_nurses_cannot_sign(
    client: TestClient, v: Visit
) -> None:
    rx = draft(client, v, "Paracetamol 500 mg", "Cetirizine 10 mg")
    upd = client.put(
        f"{API}/prescriptions/{rx['id']}", headers=v.doctor, json=rx_body("Ibuprofen 400 mg")
    )
    assert upd.status_code == 200 and [i["medicine_name"] for i in upd.json()["items"]] == [
        "Ibuprofen 400 mg"
    ]
    for h in (v.nurse, v.recep, v.admin):
        assert post(client, h, f"/prescriptions/{rx['id']}/sign").status_code == 403


def test_pharmacist_sees_only_signed_prescriptions(client: TestClient, v: Visit, org_a: H) -> None:
    record_nka(client, v)
    d1 = draft(client, v, "Paracetamol 500 mg")
    d2 = draft(client, v, "Cetirizine 10 mg")
    post(client, v.doctor, f"/prescriptions/{d1['id']}/sign")
    ph, _ = make_staff(client, org_a, "ph@alpha-clinic.example.com", "pharmacist", "alpha-clinic")
    assert get(client, ph, f"/prescriptions/{d1['id']}").status_code == 200
    assert get(client, ph, f"/prescriptions/{d2['id']}").status_code == 404
    listed = get(client, ph, f"/patients/{v.patient['id']}/prescriptions").json()
    assert [r["id"] for r in listed] == [d1["id"]]
    assert post(client, ph, f"/prescriptions/{d2['id']}/sign").status_code == 403
    assert post(client, ph, f"/prescriptions/{d2['id']}/safety-check").status_code == 403


def test_prescription_isolated_by_tenant(client: TestClient, v: Visit, org_b: H) -> None:
    rx = draft(client, v, "Paracetamol 500 mg")
    doc_b, _ = make_staff(client, org_b, "dr@beta.example.com", "doctor", "beta-hospital")
    assert get(client, doc_b, f"/prescriptions/{rx['id']}").status_code == 404
    assert post(client, doc_b, f"/prescriptions/{rx['id']}/sign").status_code == 404
    assert (
        post(client, doc_b, f"/prescriptions/{rx['id']}/void", {"reason": "nope nope"}).status_code
        == 404
    )


def test_signing_is_audited_without_prescription_content(client: TestClient, v: Visit) -> None:
    record_nka(client, v)
    rx = draft(client, v, "Zzyzxcillin 500 mg")
    post(client, v.doctor, f"/prescriptions/{rx['id']}/sign")
    logs = get(client, v.admin, "/audit-logs", action="PRESCRIPTION_SIGNED").json()
    assert len(logs) == 1 and "zzyzx" not in str(logs).lower()
    kinds = [
        e["event_type"]
        for e in get(client, v.doctor, f"/patients/{v.patient['id']}/timeline").json()
    ]
    assert "PRESCRIPTION_SIGNED" in kinds and "PRESCRIPTION_DRAFTED" in kinds
