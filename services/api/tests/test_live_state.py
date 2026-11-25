"""Live recording state shared between API processes: the latest partial line of a session, and the
claim that keeps one audio connection per session. The Redis tests run when AAROGYA_TEST_REDIS_URL
points at a Redis that may be written to (CI provides one)."""

import os
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import set_tenant
from app.modules.interactions.service import interrupt_after_restart
from app.speech import live
from tests.speech_helpers import recording_ready, start_session, token_of, transcript
from tests.test_gateway import authed, closes_with, connect

H = dict[str, str]
REDIS_URL = os.environ.get("AAROGYA_TEST_REDIS_URL", "")
needs_redis = pytest.mark.skipif(not REDIS_URL, reason="AAROGYA_TEST_REDIS_URL is not set")


def redis_backend(prefix: str) -> live.RedisLive:
    import redis

    return live.RedisLive(redis.Redis.from_url(REDIS_URL), prefix=prefix)


@pytest.fixture(params=["memory", "redis"])
def two(request: pytest.FixtureRequest) -> tuple[Any, Any]:
    """Two processes' views of the live state."""
    if request.param == "memory":
        one = live.MemoryLive()
        return one, one  # in memory there is only ever one process
    if not REDIS_URL:
        pytest.skip("AAROGYA_TEST_REDIS_URL is not set")
    prefix = f"aarogya:test:{uuid.uuid4().hex}:"
    return redis_backend(prefix), redis_backend(prefix)


def test_one_connection_per_session_and_only_its_holder_can_renew_or_release(
    two: tuple[Any, Any],
) -> None:
    a, b = two
    iid = uuid.uuid4()
    token = a.claim(iid)
    assert token and b.claim(iid) is None
    assert b.renew(iid, "someone-else") is False
    b.release(iid, "someone-else")
    assert b.claim(iid) is None  # a wrong token released nothing
    assert a.renew(iid, token) is True
    assert b.claimed([iid, uuid.uuid4()]) == {iid}
    a.release(iid, token)
    assert b.claimed([iid]) == set()
    assert b.claim(iid) is not None


def test_a_claim_lapses_if_its_holder_stops_renewing(
    two: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = two
    monkeypatch.setattr(live, "CLAIM_SECONDS", 0.2)
    iid = uuid.uuid4()
    first = a.claim(iid)
    assert first and b.claim(iid) is None
    time.sleep(0.35)
    assert b.claim(iid) is not None  # the first holder is presumed gone
    assert a.renew(iid, first) is False


def test_the_partial_line_is_seen_by_every_process_and_expires(
    two: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = two
    iid = uuid.uuid4()
    a.set_partial(iid, live.LivePartial("BP is one forty", "S1", "en-IN"))
    assert b.get_partial(iid) == live.LivePartial("BP is one forty", "S1", "en-IN")
    b.clear(iid)
    assert a.get_partial(iid) is None
    monkeypatch.setattr(live, "PARTIAL_SECONDS", 0.2)
    a.set_partial(iid, live.LivePartial("still talking", None, None))
    time.sleep(0.35)
    assert b.get_partial(iid) is None


def test_without_redis_partials_are_skipped_and_duplicates_on_one_process_are_still_refused() -> (
    None
):
    import redis

    down = live.RedisLive(redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.1))
    iid = uuid.uuid4()
    down.set_partial(iid, live.LivePartial("x", None, None))
    assert down.get_partial(iid) is None
    token = down.claim(iid)
    assert token is not None and down.claim(iid) is None
    assert down.renew(iid, token) is True
    down.release(iid, token)
    assert down.claim(iid) is not None
    assert down.claimed([iid]) == {iid}  # unknown is treated as live, never paused
    assert down.unavailable > 0


def test_with_redis_several_instances_may_serve_recordings_in_production() -> None:
    strong = {
        "environment": "production",
        "jwt_secret": "s" * 48,
        "field_encryption_key": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE=",
        "database_url": "postgresql+psycopg://u:p@db/x",
        "cors_origins": ["https://clinic.example.com"],
    }
    assert Settings(**strong).single_instance_guard is True  # type: ignore[arg-type]
    shared = Settings(**strong, redis_url="redis://redis:6379/0")  # type: ignore[arg-type]
    assert shared.single_instance_guard is False


# ---- the gateway and start-up with state shared in Redis ----------------------------------------


@pytest.fixture
def shared(client: TestClient) -> Iterator[live.RedisLive]:
    """This app's live state in Redis, plus a second process's view of the same Redis."""
    if not REDIS_URL:
        pytest.skip("AAROGYA_TEST_REDIS_URL is not set")
    import redis

    redis.Redis.from_url(REDIS_URL).flushdb()
    live.configure(REDIS_URL)
    try:
        yield redis_backend("aarogya:live:")
    finally:
        live.configure("")


@needs_redis
def test_a_second_connection_on_another_instance_is_refused(
    client: TestClient, org_a: H, shared: live.RedisLive
) -> None:
    v = recording_ready(client, org_a)
    session = start_session(client, v)
    iid = uuid.UUID(session["interaction"]["id"])
    held = shared.claim(iid)  # another instance is serving this session
    assert held
    with connect(client, session, None) as ws:
        ws.send_json({"type": "auth", "token": token_of(v.doctor)})
        assert closes_with(ws) == 4409
    shared.release(iid, held)
    with connect(client, session, None) as ws:
        assert authed(ws, token_of(v.doctor))["type"] == "ready"
        assert shared.claimed([iid]) == {iid}  # this instance holds it now, visibly to others
        ws.send_json({"type": "stop"})
        closes_with(ws)
    assert shared.claimed([iid]) == set()  # released when the connection ended


@needs_redis
def test_a_partial_line_from_another_instance_is_shown(
    client: TestClient, org_a: H, shared: live.RedisLive
) -> None:
    v = recording_ready(client, org_a)
    session = start_session(client, v)
    iid = session["interaction"]["id"]
    shared.set_partial(uuid.UUID(iid), live.LivePartial("Fever since two days", "S1", "en-IN"))
    assert transcript(client, v.doctor, iid)["partial"]["text"] == "Fever since two days"


@needs_redis
def test_starting_an_instance_pauses_only_recordings_no_instance_is_serving(
    client: TestClient, org_a: H, shared: live.RedisLive, db: Session
) -> None:
    v = recording_ready(client, org_a)
    iid = start_session(client, v)["interaction"]["id"]

    def mark_active() -> None:
        set_tenant(db, None, bypass=True)
        db.execute(
            text("update clinical_interactions set status = 'ACTIVE' where id = :i"), {"i": iid}
        )
        db.commit()

    def status() -> str:
        set_tenant(db, None, bypass=True)
        q = text("select status from clinical_interactions where id = :i")
        return str(db.execute(q, {"i": iid}).scalar())

    mark_active()
    held = shared.claim(uuid.UUID(iid))  # another running instance is serving it
    assert held
    assert interrupt_after_restart(db) == 0 and status() == "ACTIVE"
    shared.release(uuid.UUID(iid), held)  # that instance has gone
    assert interrupt_after_restart(db) == 1 and status() == "PAUSED"
