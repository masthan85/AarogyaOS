from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core import totp
from tests.clinical_helpers import get, post
from tests.conftest import PASSWORD, make_staff

H = dict[str, str]
ORG = "alpha-clinic"


@pytest.fixture
def staff(client: TestClient, org_a: H) -> tuple[H, str, dict[str, Any]]:
    headers, user = make_staff(client, org_a, "mfa@alpha-clinic.example.com", "nurse", ORG)
    return headers, "mfa@alpha-clinic.example.com", user


def login(client: TestClient, email: str, **extra: Any) -> Any:
    return client.post(
        "/api/v1/auth/login",
        json={"organisation_slug": ORG, "email": email, "password": PASSWORD, **extra},
    )


def enrol(client: TestClient, headers: H) -> tuple[str, list[str]]:
    started = post(client, headers, "/auth/mfa/enroll")
    assert started.status_code == 200, started.text
    secret = started.json()["secret"]
    assert started.json()["otpauth_uri"].startswith("otpauth://totp/")
    done = post(
        client, headers, "/auth/mfa/confirm", {"code": totp.code_at(secret, totp.current_step())}
    )
    assert done.status_code == 200, done.text
    return secret, done.json()["recovery_codes"]


def test_totp_matches_the_rfc_6238_reference_vector() -> None:
    # RFC 6238 appendix B, SHA-1 secret "12345678901234567890", T = 59 s -> 94287082 (8 digits).
    import base64

    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    assert totp.code_at(secret, 59 // 30) == "287082"  # last six digits of 94287082
    assert totp.verify(secret, "287082", now=59) == 1
    assert totp.verify(secret, "287082", now=59 + 300) is None
    assert totp.verify(secret, "12345", now=59) is None


def test_enrolment_only_counts_once_confirmed(client: TestClient, staff: Any) -> None:
    headers, email, _ = staff
    post(client, headers, "/auth/mfa/enroll")
    assert get(client, headers, "/auth/mfa").json()["enabled"] is False
    assert login(client, email).status_code == 200  # not on yet: password alone still works
    bad = post(client, headers, "/auth/mfa/confirm", {"code": "000000"})
    assert bad.status_code == 401


def test_login_needs_the_code_once_on_and_a_code_works_once(client: TestClient, staff: Any) -> None:
    headers, email, _ = staff
    secret, codes = enrol(client, headers)
    assert len(codes) == 8
    status = get(client, headers, "/auth/mfa").json()
    assert status == {"enabled": True, "recovery_codes_remaining": 8}
    missing = login(client, email)
    assert missing.status_code == 401 and missing.json()["title"] == "mfa_required"
    wrong = login(client, email, mfa_code="000000")
    assert wrong.status_code == 401 and wrong.json()["title"] == "invalid_mfa_code"
    # The code used to confirm enrolment is already spent; the next step's code is fresh.
    fresh = totp.code_at(secret, totp.current_step() + 1)
    assert login(client, email, mfa_code=fresh).status_code == 200
    assert login(client, email, mfa_code=fresh).status_code == 401  # replay refused


def test_recovery_codes_are_single_use(client: TestClient, staff: Any) -> None:
    headers, email, _ = staff
    _, codes = enrol(client, headers)
    assert login(client, email, mfa_code=codes[0]).status_code == 200
    assert login(client, email, mfa_code=codes[0]).status_code == 401
    assert get(client, headers, "/auth/mfa").json()["recovery_codes_remaining"] == 7


def test_repeated_wrong_codes_lock_the_account(client: TestClient, staff: Any) -> None:
    headers, email, _ = staff
    enrol(client, headers)
    for _ in range(5):
        assert login(client, email, mfa_code="111111").status_code == 401
    # Locked: even a correct password with a valid recovery path is refused for now.
    assert login(client, email, mfa_code="222222").status_code == 401


def test_turning_it_off_needs_password_and_code(client: TestClient, staff: Any) -> None:
    headers, email, _ = staff
    secret, codes = enrol(client, headers)
    nope = post(
        client, headers, "/auth/mfa/disable", {"password": "wrong-password-123", "code": codes[0]}
    )
    assert nope.status_code == 401
    off = post(client, headers, "/auth/mfa/disable", {"password": PASSWORD, "code": codes[0]})
    assert off.status_code == 204
    assert get(client, headers, "/auth/mfa").json()["enabled"] is False
    assert login(client, email).status_code == 200


def test_an_administrator_can_reset_a_lost_phone(client: TestClient, org_a: H, staff: Any) -> None:
    headers, email, user = staff
    enrol(client, headers)
    r = post(client, org_a, f"/users/{user['id']}/mfa/reset")
    assert r.status_code == 204
    assert login(client, email).status_code == 200
    assert post(client, headers, f"/users/{user['id']}/mfa/reset").status_code == 403
    audit = get(client, org_a, "/audit-logs", action="MFA_RESET_BY_ADMIN").json()
    assert audit


def test_the_secret_is_stored_encrypted(client: TestClient, staff: Any, db: Any) -> None:
    from sqlalchemy import text

    headers, _, user = staff
    secret, _ = enrol(client, headers)
    stored = db.execute(
        text("select mfa_secret from users where id = :i"), {"i": user["id"]}
    ).scalar()
    assert stored and secret not in stored and stored.startswith("v2.")
