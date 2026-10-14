from fastapi.testclient import TestClient

from tests.conftest import PASSWORD, make_staff


def test_doctor_can_read_structure_but_not_manage(
    client: TestClient, org_a: dict[str, str]
) -> None:
    doc, _ = make_staff(client, org_a, "dr@alpha-clinic.example.com", "doctor", "alpha-clinic")
    assert client.get("/api/v1/facilities", headers=doc).status_code == 200
    assert (
        client.post("/api/v1/facilities", headers=doc, json={"name": "x", "code": "X"}).status_code
        == 403
    )
    assert client.get("/api/v1/users", headers=doc).status_code == 403
    assert client.get("/api/v1/audit-logs", headers=doc).status_code == 403


def test_denied_access_is_audited(client: TestClient, org_a: dict[str, str]) -> None:
    nurse, _ = make_staff(client, org_a, "nurse@alpha-clinic.example.com", "nurse", "alpha-clinic")
    client.get("/api/v1/users", headers=nurse)
    logs = client.get(
        "/api/v1/audit-logs", headers=org_a, params={"action": "ACCESS_DENIED"}
    ).json()
    assert len(logs) == 1
    assert logs[0]["outcome"] == "DENIED" and logs[0]["reason"] == "user:read"


def test_every_non_admin_clinical_role_is_denied_admin_actions(
    client: TestClient, org_a: dict[str, str]
) -> None:
    for i, role in enumerate(
        [
            "doctor",
            "nurse",
            "receptionist",
            "lab_technician",
            "radiology_technician",
            "pharmacist",
            "billing_staff",
        ]
    ):
        h, _ = make_staff(client, org_a, f"u{i}@alpha-clinic.example.com", role, "alpha-clinic")
        assert (
            client.post(
                "/api/v1/users",
                headers=h,
                json={
                    "email": f"x{i}@alpha-clinic.example.com",
                    "full_name": "x",
                    "password": PASSWORD,
                    "roles": ["hospital_admin"],
                },
            ).status_code
            == 403
        ), role
        assert (
            client.post(
                "/api/v1/organisations",
                headers=h,
                json={
                    "name": "evil",
                    "slug": "evil-org",
                    "admin_email": "e@e.example.com",
                    "admin_full_name": "e",
                    "admin_password": PASSWORD,
                },
            ).status_code
            == 403
        ), role


def test_tenant_admin_cannot_escalate_to_platform_role(
    client: TestClient, org_a: dict[str, str]
) -> None:
    r = client.post(
        "/api/v1/users",
        headers=org_a,
        json={
            "email": "sneaky@alpha-clinic.example.com",
            "full_name": "s",
            "password": PASSWORD,
            "roles": ["super_admin"],
        },
    )
    assert r.status_code == 403
    _, user = make_staff(client, org_a, "dr@alpha-clinic.example.com", "doctor", "alpha-clinic")
    assert (
        client.put(
            f"/api/v1/users/{user['id']}/roles", headers=org_a, json={"roles": ["super_admin"]}
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/api/v1/users/{user['id']}/roles", headers=org_a, json={"roles": ["nonexistent"]}
        ).status_code
        == 400
    )


def test_platform_admin_has_no_access_to_tenant_data(
    client: TestClient, platform_headers: dict[str, str], org_a: dict[str, str]
) -> None:
    client.post("/api/v1/facilities", headers=org_a, json={"name": "x", "code": "X"})
    for path in (
        "/api/v1/facilities",
        "/api/v1/users",
        "/api/v1/audit-logs",
        "/api/v1/departments",
    ):
        assert client.get(path, headers=platform_headers).status_code == 403, path
    orgs = client.get("/api/v1/organisations", headers=platform_headers)
    assert orgs.status_code == 200 and len(orgs.json()) == 1


def test_role_change_is_audited_with_before_and_after(
    client: TestClient, org_a: dict[str, str]
) -> None:
    _, user = make_staff(client, org_a, "dr@alpha-clinic.example.com", "doctor", "alpha-clinic")
    client.put(f"/api/v1/users/{user['id']}/roles", headers=org_a, json={"roles": ["nurse"]})
    log = client.get(
        "/api/v1/audit-logs", headers=org_a, params={"action": "USER_ROLES_CHANGED"}
    ).json()[0]
    assert log["before"] == {"roles": ["doctor"]} and log["after"] == {"roles": ["nurse"]}


def test_admin_cannot_deactivate_self(client: TestClient, org_a: dict[str, str]) -> None:
    me = client.get("/api/v1/auth/me", headers=org_a).json()
    assert client.post(f"/api/v1/users/{me['id']}/deactivate", headers=org_a).status_code == 400


def test_validation_errors_do_not_echo_submitted_values(
    client: TestClient, org_a: dict[str, str]
) -> None:
    r = client.post(
        "/api/v1/users",
        headers=org_a,
        json={
            "email": "a@b.example.com",
            "full_name": "x",
            "password": "short",
            "roles": ["doctor"],
        },
    )
    assert r.status_code == 422
    assert "short" not in r.text.replace("too_short", "").replace("String should", "")
