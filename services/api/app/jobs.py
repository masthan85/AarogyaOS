"""Scheduled maintenance jobs: `python -m app.cli run-job NAME`, from cron or a Kubernetes CronJob.

Each run takes a database advisory lock, so two schedulers (or a slow run overlapping the next) can
never execute the same job at once; the loser records SKIPPED. Every run leaves a PHI-free row in
`job_runs` (counts and an error code, never data or exception text), and the metrics endpoint
reports when each job last succeeded so a silent scheduler failure is visible.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.crypto import FieldCrypto
from app.core.db import set_tenant
from app.modules.identity.models import RefreshToken
from app.modules.interactions.models import ClinicalInteraction
from app.modules.interactions.retention import purge_due_audio
from app.modules.interactions.service import STALE_AFTER
from app.modules.ops.models import JobRun
from app.speech.audio_store import LocalEncryptedAudioStore

log = logging.getLogger("aarogya.jobs")
REFRESH_TOKEN_KEEP = timedelta(days=30)  # kept past expiry so reuse of a stolen token is still seen

JobFn = Callable[[Session, Settings], dict[str, int]]


def purge_audio(session: Session, settings: Settings) -> dict[str, int]:
    store = LocalEncryptedAudioStore(
        settings.audio_store_path, FieldCrypto(settings.field_encryption_key)
    )
    return {"removed": purge_due_audio(session, store)}


def pause_stale_recordings(session: Session, settings: Settings) -> dict[str, int]:
    """A recording whose audio stopped arriving must not keep claiming to be live."""
    set_tenant(session, None, bypass=True)
    cutoff = datetime.now(UTC) - STALE_AFTER
    result = session.execute(
        update(ClinicalInteraction)
        .where(ClinicalInteraction.status == "ACTIVE", ClinicalInteraction.last_audio_at < cutoff)
        .values(status="PAUSED", pause_reason="CONNECTION_LOST")
    )
    session.commit()
    return {"paused": result.rowcount or 0}  # type: ignore[attr-defined]


def purge_refresh_tokens(session: Session, settings: Settings) -> dict[str, int]:
    set_tenant(session, None, bypass=True)
    result = session.execute(
        delete(RefreshToken).where(RefreshToken.expires_at < datetime.now(UTC) - REFRESH_TOKEN_KEEP)
    )
    session.commit()
    return {"deleted": result.rowcount or 0}  # type: ignore[attr-defined]


JOBS: dict[str, JobFn] = {
    "purge-audio": purge_audio,
    "pause-stale-recordings": pause_stale_recordings,
    "purge-refresh-tokens": purge_refresh_tokens,
}


def run_job(maker: sessionmaker[Session], settings: Settings, name: str) -> JobRun:
    if name not in JOBS:
        raise KeyError(name)
    with maker() as lock_session:
        got = lock_session.scalar(
            text("select pg_try_advisory_lock(hashtext(:n))"), {"n": f"job:{name}"}
        )
        try:
            with maker() as ledger:
                run = JobRun(name=name, status="RUNNING" if got else "SKIPPED")
                set_tenant(ledger, None, bypass=True)
                ledger.add(run)
                ledger.commit()
                run_id = run.id
            if not got:
                _finish(maker, run_id, "SKIPPED", {}, "ALREADY_RUNNING")
                return _load(maker, run_id)
            try:
                with maker() as work:
                    result = JOBS[name](work, settings)
                _finish(maker, run_id, "OK", result, None)
            except Exception as exc:  # noqa: BLE001  (record and move on; never log the message)
                log.error("job failed", extra={"job": name, "error": type(exc).__name__})
                _finish(maker, run_id, "FAILED", {}, type(exc).__name__[:60])
            return _load(maker, run_id)
        finally:
            if got:
                lock_session.execute(
                    text("select pg_advisory_unlock(hashtext(:n))"), {"n": f"job:{name}"}
                )


def _finish(
    maker: sessionmaker[Session],
    run_id: object,
    status: str,
    result: dict[str, int],
    error: str | None,
) -> None:
    with maker() as s:
        set_tenant(s, None, bypass=True)
        run = s.get(JobRun, run_id)
        assert run is not None
        run.status, run.result, run.error_code = status, result, error
        run.finished_at = datetime.now(UTC)
        s.commit()


def _load(maker: sessionmaker[Session], run_id: object) -> JobRun:
    with maker() as s:
        set_tenant(s, None, bypass=True)
        run = s.get(JobRun, run_id)
        assert run is not None
        s.expunge(run)
        return run


def last_success(session: Session) -> dict[str, datetime]:
    rows = session.execute(
        select(JobRun.name, JobRun.finished_at)
        .where(JobRun.status == "OK")
        .order_by(JobRun.finished_at)
    )
    return {name: at for name, at in rows if at is not None}
