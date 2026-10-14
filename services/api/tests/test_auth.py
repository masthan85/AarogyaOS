from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.conftest import PASSWORD, login, make_staff


def test_login_returns_tokens_and_me(client: TestClient, org_a: dict[str, str]) -> None:
    r = client.get("/api/v1/auth/me", headers=org_a)
    assert r.status_code == 200
    body = r.json()
    assert body["roles"] == ["hospital_admin"]
    assert "user:manage" in body["permissions"]


def test_wrong_password_and_unknown_user_look_identical(
    client: TestClient, org_a: dict[str, str]
) -> None:
    bad_pw = login(client, "admin@alpha-clinic.example.com", "wrong-password-xx", "alpha-clinic")
    unknown = login(client, "nobody@alpha-clinic.example.com", PASSWORD, "alpha-clinic")
    bad_org = login(client, "admin@alpha-clinic.example.com", PASSWORD, "no-such-org")
    assert bad_pw.status_code == unknown.status_code == bad_org.status_code == 401
    assert bad_pw.json()["detail"] == unknown.json()["detail"] == bad_org.json()["detail"]


def test_same_email_in_other_org_does_not_authenticate(
    client: TestClient, org_a: dict[str, str], org_b: dict[str, str]
) -> None:
    assert (
        login(client, "admin@alpha-clinic.example.com", PASSWORD, "beta-hospital").status_code
        == 401
    )


def test_lockout_after_repeated_failures(client: TestClient, org_a: dict[str, str]) -> None:
    for _ in range(3):
        assert (
            login(
                client, "admin@alpha-clinic.example.com", "nope-nope-nope", "alpha-clinic"
            ).status_code
            == 401
        )
    # Correct password is now refused while locked.
    assert (
        login(client, "admin@alpha-clinic.example.com", PASSWORD, "alpha-clinic").status_code == 401
    )


def test_requests_without_or_with_bad_token_are_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401
    )


def test_expired_and_tampered_tokens_rejected(
    client: TestClient, org_a: dict[str, str], settings: Settings
) -> None:
    token = org_a["Authorization"].split()[1]
    claims = jwt.decode(token, options={"verify_signature": False})
    expired = jwt.encode(
        {**claims, "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    forged = jwt.encode(claims, "some-other-secret-some-other-secret-xx", algorithm="HS256")
    for bad in (expired, forged):
        assert (
            client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad}"}).status_code
            == 401
        )


def test_refresh_rotates_and_reuse_revokes_family(
    client: TestClient, org_a: dict[str, str]
) -> None:
    first = login(client, "admin@alpha-clinic.example.com", PASSWORD, "alpha-clinic").json()
    second = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert second.status_code == 200
    assert second.json()["refresh_token"] != first["refresh_token"]

    # Replaying the old token is treated as theft: the whole session family dies.
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert replay.status_code == 401
    legit = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": second.json()["refresh_token"]}
    )
    assert legit.status_code == 401
    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {second.json()['access_token']}"}
    )
    assert me.status_code == 401


def test_logout_invalidates_access_token_immediately(
    client: TestClient, org_a: dict[str, str]
) -> None:
    pair = login(client, "admin@alpha-clinic.example.com", PASSWORD, "alpha-clinic").json()
    headers = {"Authorization": f"Bearer {pair['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert (
        client.post(
            "/api/v1/auth/logout", json={"refresh_token": pair["refresh_token"]}
        ).status_code
        == 204
    )
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_deactivated_user_loses_access(client: TestClient, org_a: dict[str, str]) -> None:
    doc, user = make_staff(
        client, org_a, "dr.rao@alpha-clinic.example.com", "doctor", "alpha-clinic"
    )
    assert client.get("/api/v1/facilities", headers=doc).status_code == 200
    assert client.post(f"/api/v1/users/{user['id']}/deactivate", headers=org_a).status_code == 200
    assert client.get("/api/v1/facilities", headers=doc).status_code == 401
    assert (
        login(client, "dr.rao@alpha-clinic.example.com", PASSWORD, "alpha-clinic").status_code
        == 401
    )
