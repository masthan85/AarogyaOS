import pytest
from fastapi.testclient import TestClient

from app.core.errors import TooManyRequests
from app.core.ratelimit import RateLimiter
from tests.conftest import PASSWORD
from tests.helpers import reception

H = dict[str, str]


def test_window_slides_and_keys_are_independent() -> None:
    rl = RateLimiter()
    for i in range(3):
        rl.check("a", limit=3, window_seconds=10, now=float(i))
    with pytest.raises(TooManyRequests) as err:
        rl.check("a", limit=3, window_seconds=10, now=3.0)
    assert err.value.extra["retry_after_seconds"] >= 1
    rl.check("b", limit=3, window_seconds=10, now=3.0)  # another key is unaffected
    rl.check("a", limit=3, window_seconds=10, now=10.5)  # the oldest attempt has expired
    rl.check("c", limit=0, window_seconds=10, now=0.0)  # zero turns the limit off
    for _ in range(50):
        rl.check("c", limit=0, window_seconds=10, now=0.0)


def test_login_is_throttled_per_address(client: TestClient, org_a: H) -> None:
    client.app.state.settings.login_attempts_per_minute_per_ip = 3  # type: ignore[attr-defined]
    client.app.state.rate_limiter = RateLimiter()  # type: ignore[attr-defined]  # forget the set-up logins
    body = {
        "organisation_slug": "alpha-clinic",
        "email": "nobody@x.example.com",
        "password": PASSWORD,
    }
    codes = [client.post("/api/v1/auth/login", json=body).status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401]
    assert codes[3:] == [429, 429]


def test_patient_search_is_throttled_per_user(client: TestClient, org_a: H) -> None:
    recep = reception(client, org_a, "alpha-clinic")
    client.app.state.settings.patient_searches_per_minute_per_user = 2  # type: ignore[attr-defined]
    codes = [
        client.get("/api/v1/patients/search", headers=recep, params={"name": "Lakshmi"}).status_code
        for _ in range(3)
    ]
    assert codes[:2] == [200, 200]
    assert codes[2] == 429
