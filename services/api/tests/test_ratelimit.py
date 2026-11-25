import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import TooManyRequests
from app.core.ratelimit import RateLimiter, RedisRateLimiter, limiter_from_url
from app.main import create_app
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


# ---- shared limits in Redis ----------------------------------------------------------------------
# These run when AAROGYA_TEST_REDIS_URL points at a Redis that may be written to (CI provides one).

REDIS_URL = os.environ.get("AAROGYA_TEST_REDIS_URL", "")
needs_redis = pytest.mark.skipif(not REDIS_URL, reason="AAROGYA_TEST_REDIS_URL is not set")


@pytest.fixture
def prefix() -> str:
    return f"aarogya:test:{uuid.uuid4().hex}:"


def redis_limiter(prefix: str) -> RedisRateLimiter:
    import redis

    return RedisRateLimiter(redis.Redis.from_url(REDIS_URL), prefix=prefix)


@needs_redis
def test_redis_window_slides_like_the_memory_one(prefix: str) -> None:
    rl = redis_limiter(prefix)
    for i in range(3):
        rl.check("a", limit=3, window_seconds=10, now=float(i))
    with pytest.raises(TooManyRequests) as err:
        rl.check("a", limit=3, window_seconds=10, now=3.0)
    assert 1 <= err.value.extra["retry_after_seconds"] <= 8
    rl.check("b", limit=3, window_seconds=10, now=3.0)
    rl.check("a", limit=3, window_seconds=10, now=10.5)
    for _ in range(20):
        rl.check("c", limit=0, window_seconds=10)


@needs_redis
def test_two_processes_share_one_limit(prefix: str) -> None:
    first, second = redis_limiter(prefix), redis_limiter(prefix)
    first.check("login:10.0.0.1", limit=2, window_seconds=60)
    second.check("login:10.0.0.1", limit=2, window_seconds=60)
    with pytest.raises(TooManyRequests):
        first.check("login:10.0.0.1", limit=2, window_seconds=60)
    with pytest.raises(TooManyRequests):
        second.check("login:10.0.0.1", limit=2, window_seconds=60)


@needs_redis
def test_the_api_uses_redis_when_configured(settings: Settings, prefix: str) -> None:
    # Two API instances, as two containers would be: guesses against one count against the other.
    settings = settings.model_copy(
        update={"redis_url": REDIS_URL, "login_attempts_per_minute_per_ip": 3}
    )
    apps = [create_app(settings), create_app(settings)]
    body = {"organisation_slug": "nowhere", "email": "nobody@x.example.com", "password": "x" * 12}
    codes = []
    with TestClient(apps[0]) as a, TestClient(apps[1]) as b:
        for app in apps:
            assert isinstance(app.state.rate_limiter, RedisRateLimiter)
            app.state.rate_limiter._prefix = prefix
        for c in (a, b, a, b, a):
            codes.append(c.post("/api/v1/auth/login", json=body).status_code)
    assert codes == [401, 401, 401, 429, 429]


def test_an_unreachable_store_lets_requests_through_and_counts_them() -> None:
    import redis

    rl = RedisRateLimiter(redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.1))
    for _ in range(5):
        rl.check("a", limit=1, window_seconds=60)
    assert rl.unavailable == 5


def test_without_a_url_limits_stay_in_memory() -> None:
    assert isinstance(limiter_from_url(""), RateLimiter)
