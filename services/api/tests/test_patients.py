from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.conftest import make_staff
from tests.helpers import make_patient, reception

BASE = "/api/v1/patients"


def test_registration_by_age_flags_estimated_dob_and_issues_sequential_mrns(
    client: TestClient, org_a: dict[str, str]
) -> None:
    r = reception(client, org_a, "alpha-clinic")
    p1 = make_patient(client, r)
    p2 = make_patient(client, r, "Ravi Teja", administrative_gender="male", mobile="9123456780")
    assert (p1["mrn"], p2["mrn"]) == ("P0000001", "P0000002")
    assert p1["dob_is_estimated"] is True and p1["age_years"] == 45
    assert p1["mobile"] == "+919876543210"


def test_registration_validation(client: TestClient, org_a: dict[str, str]) -> None:
    r = reception(client, org_a, "alpha-clinic")
    ok = {"full_name": "Asha Rani", "age_years": 30}
    assert client.post(BASE, headers=r, json={"full_name": "Asha Rani"}).status_code == 422
    assert client.post(BASE, headers=r, json={**ok, "mobile": "12345"}).status_code == 422
    assert client.post(BASE, headers=r, json={**ok, "age_years": 200}).status_code == 422
    assert (
        client.post(BASE, headers=r, json={**ok, "date_of_birth": "2999-01-01"}).status_code == 422
    )
    assert (
        client.post(BASE, headers=r, json={**ok, "preferred_language": "not a tag!"}).status_code
        == 422
    )


def test_search_returns_minimal_fields_only(client: TestClient, org_a: dict[str, str]) -> None:
    r = reception(client, org_a, "alpha-clinic")
    make_patient(client, r, address="12 Gandhi Road", emergency_contact_name="Ramu")
    hits = client.get(f"{BASE}/search", headers=r, params={"name": "laksh"}).json()
    assert len(hits) == 1
    assert set(hits[0]) == {
        "id",
        "mrn",
        "full_name",
        "age_years",
        "administrative_gender",
        "mobile_masked",
    }
    assert hits[0]["mobile_masked"] == "+91 XXXXXX3210"


def test_search_by_mobile_mrn_and_name_tokens(client: TestClient, org_a: dict[str, str]) -> None:
    r = reception(client, org_a, "alpha-clinic")
    p = make_patient(client, r, "Venkata Subba Rao", administrative_gender="male")
    make_patient(client, r, "Lakshmi Devi", mobile="9000000001")
    by_mobile = client.get(f"{BASE}/search", headers=r, params={"mobile": "+91 98765 43210"}).json()
    assert [h["id"] for h in by_mobile] == [p["id"]]
    assert (
        client.get(f"{BASE}/search", headers=r, params={"mrn": p["mrn"].lower()}).json()[0]["id"]
        == p["id"]
    )
    assert len(client.get(f"{BASE}/search", headers=r, params={"name": "rao subba"}).json()) == 1


def test_search_refuses_broad_or_empty_queries(client: TestClient, org_a: dict[str, str]) -> None:
    r = reception(client, org_a, "alpha-clinic")
    make_patient(client, r)
    for params in ({}, {"name": "la"}, {"name": "%"}, {"mobile": "123"}):
        assert client.get(f"{BASE}/search", headers=r, params=params).status_code == 400, params
    # Wildcard characters are neutralised, never interpreted as LIKE patterns.
    assert client.get(f"{BASE}/search", headers=r, params={"name": "la_shmi"}).json() == []
    assert client.get(f"{BASE}/search", headers=r, params={"name": "l%k%"}).status_code == 400


def test_search_audit_records_counts_not_query_text(
    client: TestClient, org_a: dict[str, str]
) -> None:
    r = reception(client, org_a, "alpha-clinic")
    make_patient(client, r, "Secretname Patient")
    client.get(f"{BASE}/search", headers=r, params={"name": "secretname"})
    logs = client.get(
        "/api/v1/audit-logs", headers=org_a, params={"action": "PATIENT_SEARCHED"}
    ).json()
    assert logs and "secretname" not in str(logs).lower()


def test_duplicate_detection_flags_same_name_and_dob(
    client: TestClient, org_a: dict[str, str]
) -> None:
    r = reception(client, org_a, "alpha-clinic")
    make_patient(
        client,
        r,
        "Mohd Rafi",
        date_of_birth="1980-03-04",
        administrative_gender="male",
        age_years=None,
    )
    resp = client.post(
        BASE, headers=r, json={"full_name": "Muhammad Rafi", "date_of_birth": "1980-03-04"}
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["title"] == "possible_duplicate"
    cand = body["candidates"][0]
    assert "same date of birth" in cand["reasons"]
    assert set(cand) == {
        "id",
        "mrn",
        "full_name",
        "age_years",
        "administrative_gender",
        "mobile_masked",
        "reasons",
    }
    # After review the user may proceed.
    ok = client.post(BASE, headers=r, json={"full_name": "Muhammad Rafi", "date_of_birth": "1980-03-04",
                                            "confirm_not_duplicate": True})  # fmt: skip
    assert ok.status_code == 201


def test_family_sharing_a_mobile_is_not_flagged_as_duplicate(
    client: TestClient, org_a: dict[str, str]
) -> None:
    r = reception(client, org_a, "alpha-clinic")
    make_patient(client, r, "Lakshmi Devi", mobile="9876543210")
    resp = client.post(
        BASE, headers=r, json={"full_name": "Suresh Kumar", "age_years": 50, "mobile": "9876543210"}
    )
    assert resp.status_code == 201


def test_abha_number_is_encrypted_at_rest_masked_in_api_and_revealed_only_with_permission(
    client: TestClient, org_a: dict[str, str], superuser_engine: Engine
) -> None:
    r = reception(client, org_a, "alpha-clinic")
    p = make_patient(
        client, r, identifiers=[{"system": "ABHA_NUMBER", "value": "91-1234-5678-9012"}]
    )
    ident = p["identifiers"][0]
    assert ident["masked"] == "XX-XXXX-XXXX-9012" and ident["verified"] is False
    assert "91-1234-5678" not in str(p)

    with superuser_engine.connect() as conn:
        stored = conn.execute(
            text("select value_ciphertext, value_index, display_hint from patient_identifiers")
        ).one()
    assert "5678" not in stored[0] and "5678" not in stored[1] and stored[2] == "XX-XXXX-XXXX-9012"

    url = f"{BASE}/{p['id']}/identifiers/{ident['id']}/reveal"
    assert client.post(url, headers=r).json()["value"] == "91-1234-5678-9012"
    doctor, _ = make_staff(client, org_a, "dr@alpha-clinic.example.com", "doctor", "alpha-clinic")
    assert client.post(url, headers=doctor).status_code == 403
    audit = client.get(
        "/api/v1/audit-logs", headers=org_a, params={"action": "IDENTIFIER_VIEWED"}
    ).json()
    assert len(audit) == 1 and "5678" not in str(audit)


def test_same_abha_cannot_belong_to_two_patients(client: TestClient, org_a: dict[str, str]) -> None:
    r = reception(client, org_a, "alpha-clinic")
    ids = [{"system": "ABHA_NUMBER", "value": "91123456789012"}]
    make_patient(client, r, "Asha Rani", identifiers=ids)
    dup = client.post(
        BASE, headers=r, json={"full_name": "Someone Else", "age_years": 20, "identifiers": ids}
    )
    assert dup.status_code == 409 and "same ABHA_NUMBER" in dup.json()["candidates"][0]["reasons"]
    forced = client.post(BASE, headers=r, json={"full_name": "Someone Else", "age_years": 20, "identifiers": ids,
                                                "confirm_not_duplicate": True})  # fmt: skip
    assert forced.status_code == 409 and forced.json()["title"] == "conflict"
    assert client.post(BASE, headers=r, json={"full_name": "Bad Id", "age_years": 20,
                       "identifiers": [{"system": "ABHA_NUMBER", "value": "123"}]}).status_code == 422  # fmt: skip


def test_update_uses_optimistic_concurrency_and_keeps_history(
    client: TestClient, org_a: dict[str, str], superuser_engine: Engine
) -> None:
    r = reception(client, org_a, "alpha-clinic")
    p = make_patient(client, r, address="Old Address")
    upd = client.patch(
        f"{BASE}/{p['id']}", headers=r, json={"expected_version": 1, "address": "New Address"}
    )
    assert (
        upd.status_code == 200
        and upd.json()["version"] == 2
        and upd.json()["address"] == "New Address"
    )
    stale = client.patch(
        f"{BASE}/{p['id']}", headers=r, json={"expected_version": 1, "address": "Other"}
    )
    assert stale.status_code == 409
    with superuser_engine.connect() as conn:
        rev = conn.execute(text("select previous_values, version from patient_revisions")).one()
    assert rev[0] == {"address": "Old Address"} and rev[1] == 1
    log = client.get(
        "/api/v1/audit-logs", headers=org_a, params={"action": "PATIENT_UPDATED"}
    ).json()[0]
    assert log["after"] == {"changed_fields": ["address"]} and "Address" not in str(log)


def test_noop_update_does_not_bump_version(client: TestClient, org_a: dict[str, str]) -> None:
    r = reception(client, org_a, "alpha-clinic")
    p = make_patient(client, r, address="Same")
    out = client.patch(
        f"{BASE}/{p['id']}", headers=r, json={"expected_version": 1, "address": "Same"}
    ).json()
    assert out["version"] == 1


def test_role_matrix_for_patient_data(client: TestClient, org_a: dict[str, str]) -> None:
    r = reception(client, org_a, "alpha-clinic")
    p = make_patient(client, r)
    pid = p["id"]
    users = {role: make_staff(client, org_a, f"{role}@alpha-clinic.example.com", role, "alpha-clinic")[0]
             for role in ("doctor", "nurse", "lab_technician", "billing_staff", "pharmacist")}  # fmt: skip

    def status(h: dict[str, str], method: str, url: str, **kw: Any) -> int:
        return client.request(method, url, headers=h, **kw).status_code

    # Administrators manage the system, not patients.
    assert status(org_a, "GET", f"{BASE}/{pid}") == 403
    assert status(org_a, "GET", f"{BASE}/search", params={"mrn": "P0000001"}) == 403
    # Doctors/nurses read but do not register or edit demographics.
    for role in ("doctor", "nurse"):
        assert status(users[role], "GET", f"{BASE}/{pid}") == 200
        assert status(users[role], "GET", f"{BASE}/{pid}/timeline") == 200
        assert status(users[role], "POST", BASE, json={"full_name": "X Y", "age_years": 3}) == 403
        assert (
            status(
                users[role], "PATCH", f"{BASE}/{pid}", json={"expected_version": 1, "address": "z"}
            )
            == 403
        )
    # Lab, pharmacy, billing can find a patient but not open the record.
    for role in ("lab_technician", "pharmacist", "billing_staff"):
        assert status(users[role], "GET", f"{BASE}/search", params={"mrn": "P0000001"}) == 200
        assert status(users[role], "GET", f"{BASE}/{pid}") == 403
        assert status(users[role], "GET", f"{BASE}/{pid}/timeline") == 403
    # Reception registers but has no clinical timeline.
    assert status(r, "GET", f"{BASE}/{pid}/timeline") == 403


def test_patient_reads_are_audited(client: TestClient, org_a: dict[str, str]) -> None:
    r = reception(client, org_a, "alpha-clinic")
    p = make_patient(client, r)
    client.get(f"{BASE}/{p['id']}", headers=r)
    log = client.get(
        "/api/v1/audit-logs", headers=org_a, params={"action": "PATIENT_VIEWED"}
    ).json()
    assert len(log) == 1 and log[0]["resource_id"] == p["id"]


def test_audit_and_events_never_contain_patient_demographics(
    client: TestClient, org_a: dict[str, str], superuser_engine: Engine
) -> None:
    r = reception(client, org_a, "alpha-clinic")
    make_patient(client, r, "Zzyzx Uniquename", address="Hidden Lane 7")
    audit = client.get("/api/v1/audit-logs", headers=org_a).text
    with superuser_engine.connect() as conn:
        events = str(conn.execute(text("select payload from clinical_events")).all())
    for blob in (audit, events):
        assert (
            "zzyzx" not in blob.lower() and "Hidden Lane" not in blob and "9876543210" not in blob
        )


def test_other_organisations_cannot_see_or_touch_patients(
    client: TestClient, org_a: dict[str, str], org_b: dict[str, str]
) -> None:
    ra = reception(client, org_a, "alpha-clinic")
    rb = reception(client, org_b, "beta-hospital", "recep@beta.example.com")
    p = make_patient(client, ra)
    assert client.get(f"{BASE}/{p['id']}", headers=rb).status_code == 404
    assert (
        client.patch(
            f"{BASE}/{p['id']}", headers=rb, json={"expected_version": 1, "address": "x"}
        ).status_code
        == 404
    )
    assert (
        client.get(f"{BASE}/{p['id']}/timeline", headers=rb).status_code == 403
    )  # no permission at all
    assert client.get(f"{BASE}/search", headers=rb, params={"mobile": "9876543210"}).json() == []
    assert client.post(f"{BASE}/{p['id']}/identifiers", headers=rb,
                       json={"system": "OTHER", "value": "ABC123"}).status_code == 404  # fmt: skip
    # Same person registering in the other organisation is NOT a duplicate across tenants.
    resp = client.post(
        BASE,
        headers=rb,
        json={"full_name": "Lakshmi Devi", "age_years": 45, "mobile": "9876543210"},
    )
    assert resp.status_code == 201 and resp.json()["mrn"] == "P0000001"
