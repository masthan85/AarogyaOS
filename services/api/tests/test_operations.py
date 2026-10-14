"""Operational behaviour: readiness, metrics, request hardening, scheduled jobs, config rules."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import set_tenant
from app.jobs import JOBS, run_job
from app.main import create_app
from tests.clinical_helpers import API, make_visit
from tests.speech_helpers import recording_ready, start_session

H = dict[str, str]


def test_ready_reports_database_and_migration_state(client: TestClient) -> None:
    r = client.get("/ready")
    assert r.status_code == 200 and r.json() == {"status": "ready", "migrations": "ok"}


def test_ready_fails_closed_when_migrations_are_pending(client: TestClient, db: Session) -> None:
    db.execute(text("update alembic_version set version_num = '0005'"))
    db.commit()
    try:
        r = client.get("/ready")
        assert r.status_code == 503 and r.json() == {"status": "migrations_pending"}
    finally:
        db.execute(text("update alembic_version set version_num = '0006'"))
        db.commit()


def test_api_responses_are_not_cacheable_and_carry_security_headers(client: TestClient) -> None:
    r = client.get(f"{API}/languages", headers={"Authorization": "Bearer x"})
    assert r.headers["cache-control"] == "no-store"
    assert (
        r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    )
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert "strict-transport-security" not in r.headers  # only behind TLS in production


def test_oversized_bodies_are_refused_before_they_are_read(client: TestClient) -> None:
    limit = client.app.state.settings.max_request_bytes  # type: ignore[attr-defined]
    r = client.post(
        f"{API}/auth/login",
        content=b"x" * (limit + 1),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 413 and r.json()["title"] == "payload_too_large"


def test_metrics_use_route_templates_not_identifiers(client: TestClient, org_a: H) -> None:
    v = make_visit(client, org_a)
    client.get(f"{API}/patients/{v.patient['id']}", headers=v.doctor)
    body = client.get("/metrics").text
    assert 'route="/patients/{patient_id}"' in body
    assert v.patient["id"] not in body and "Lakshmi" not in body
    assert "aarogya_http_request_duration_seconds_bucket" in body


def test_metrics_need_the_token_when_one_is_set_and_are_off_in_production_without_one(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings.model_copy(update={"metrics_token": "s3cret-token"}))) as c:
        assert c.get("/metrics").status_code == 401
        assert c.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert (
            c.get("/metrics", headers={"Authorization": "Bearer s3cret-token"}).status_code == 200
        )


# ---- production configuration ----------------------------------------------------------------


def _prod(**kw: Any) -> Settings:
    base: dict[str, Any] = {
        "environment": "production",
        "jwt_secret": "x" * 40,
        "field_encryption_key": "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVowMTIzNDU=",
        "database_url": "postgresql+psycopg://aarogya_app:real-password@db/aarogya",
    }
    return Settings(**{**base, **kw})


def test_production_refuses_unsafe_configuration() -> None:
    assert _prod().environment == "production"
    for bad in (
        {"cors_origins": ["*"]},
        {"database_url": "postgresql+psycopg://aarogya_app:aarogya_app@db/aarogya"},
        {"jwt_secret": "short"},
    ):
        with pytest.raises(ValueError):
            _prod(**bad)


def test_production_never_defaults_to_development_providers() -> None:
    s = _prod()
    assert s.speech_provider == "" and s.llm_provider == "" and s.embedding_provider == ""


# ---- scheduled jobs --------------------------------------------------------------------------


def test_every_job_runs_records_a_phi_free_ledger_row_and_is_idempotent(
    client: TestClient, settings: Settings, db: Session
) -> None:
    maker = client.app.state.sessionmaker  # type: ignore[attr-defined]
    for name in JOBS:
        first = run_job(maker, settings, name)
        again = run_job(maker, settings, name)
        assert first.status == "OK" and again.status == "OK"
    rows = db.execute(text("select name, status, result, error_code from job_runs")).all()
    assert len(rows) == 2 * len(JOBS) and all(r[1] == "OK" and r[3] is None for r in rows)


def test_a_job_that_is_already_running_is_skipped_not_doubled(
    client: TestClient, settings: Settings, db: Session
) -> None:
    maker = client.app.state.sessionmaker  # type: ignore[attr-defined]
    with maker() as holder:
        assert holder.scalar(text("select pg_try_advisory_lock(hashtext('job:purge-audio'))"))
        skipped = run_job(maker, settings, "purge-audio")
        holder.execute(text("select pg_advisory_unlock(hashtext('job:purge-audio'))"))
    assert skipped.status == "SKIPPED" and skipped.error_code == "ALREADY_RUNNING"
    assert run_job(maker, settings, "purge-audio").status == "OK"


def test_a_failing_job_is_recorded_without_leaking_the_message(
    client: TestClient, settings: Settings, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: Session, s: Settings) -> dict[str, int]:
        raise RuntimeError("patient Lakshmi Devi has chest pain")

    monkeypatch.setitem(JOBS, "purge-audio", boom)
    run = run_job(client.app.state.sessionmaker, settings, "purge-audio")  # type: ignore[attr-defined]
    assert run.status == "FAILED" and run.error_code == "RuntimeError"
    assert "Lakshmi" not in str(db.execute(text("select * from job_runs")).all())


def test_stale_recordings_are_paused_by_the_job(
    client: TestClient, org_a: H, settings: Settings, db: Session
) -> None:
    v = recording_ready(client, org_a)
    session = start_session(client, v)
    iid = session["interaction"]["id"]
    set_tenant(db, None, bypass=True)
    db.execute(
        text("update clinical_interactions set last_audio_at = :t where id = :i"),
        {"t": datetime.now(UTC) - timedelta(minutes=5), "i": iid},
    )
    db.commit()
    run = run_job(client.app.state.sessionmaker, settings, "pause-stale-recordings")  # type: ignore[attr-defined]
    assert run.result == {"paused": 1}
    row = db.execute(
        text("select status, pause_reason from clinical_interactions where id = :i"), {"i": iid}
    ).one()
    assert tuple(row) == ("PAUSED", "CONNECTION_LOST")


def test_old_refresh_tokens_are_purged_but_recent_ones_are_kept(
    client: TestClient, org_a: H, settings: Settings, db: Session
) -> None:
    set_tenant(db, None, bypass=True)
    before = db.execute(text("select count(*) from refresh_tokens")).scalar() or 0
    assert before > 0
    db.execute(
        text(
            "update refresh_tokens set expires_at = now() - interval '40 days' where id = (select id from refresh_tokens limit 1)"
        )
    )
    db.commit()
    run = run_job(client.app.state.sessionmaker, settings, "purge-refresh-tokens")  # type: ignore[attr-defined]
    assert run.result == {"deleted": 1}
    assert db.execute(text("select count(*) from refresh_tokens")).scalar() == before - 1


def test_metrics_report_when_each_job_last_succeeded(
    client: TestClient, settings: Settings
) -> None:
    run_job(client.app.state.sessionmaker, settings, "purge-audio")  # type: ignore[attr-defined]
    assert (
        'aarogya_job_last_success_timestamp_seconds{job="purge-audio"}'
        in client.get("/metrics").text
    )
