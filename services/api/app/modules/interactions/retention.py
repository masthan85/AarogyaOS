"""Audio retention: delete audio when its time is up or the patient withdraws consent."""

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.context import RequestMeta
from app.core.db import set_tenant
from app.modules.audit.service import record_audit
from app.modules.interactions.models import AudioAsset
from app.speech.audio_store import AudioStore


def purge_due_audio(session: Session, store: AudioStore, now: datetime | None = None) -> int:
    """Delete audio whose retention ended or whose purge was requested. Returns files removed.

    Meant to run on a schedule (`python -m app.cli purge-audio`). Transcripts are NOT touched:
    they are part of the medical record and follow the record's own retention rules.
    """
    now = now or datetime.now(UTC)
    set_tenant(session, None, bypass=True)
    due = session.scalars(
        select(AudioAsset)
        .where(
            AudioAsset.deleted_at.is_(None),
            or_(AudioAsset.purge_requested_at.is_not(None), AudioAsset.retain_until <= now),
        )
        .with_for_update()
    ).all()
    removed = 0
    for asset in due:
        if asset.storage_key:
            store.delete(asset.storage_key)
        reason = asset.purge_reason or "RETENTION_EXPIRED"
        asset.storage_key, asset.deleted_at = None, now
        removed += 1
        record_audit(
            session,
            RequestMeta(None, None, None),
            org_id=asset.organisation_id,
            actor_user_id=None,
            action="AUDIO_PURGED",
            resource_type="audio_asset",
            resource_id=asset.id,
            reason=reason,
        )
    session.commit()
    return removed
