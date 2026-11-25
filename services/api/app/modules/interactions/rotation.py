"""Re-encrypt retained audio under the current field key, after `rotate-field-key`.

Only recordings that have ended are touched: a paused one can resume and append to its file. Those
are counted and left for the next run. Content is never changed, only the key it is sealed with.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import set_tenant
from app.modules.interactions.models import AudioAsset, ClinicalInteraction
from app.speech.audio_store import AudioStore


@dataclass
class AudioRotation:
    reencrypted: int = 0
    already_current: int = 0
    still_recording: int = 0
    missing: int = 0


def rotate_audio(session: Session, store: AudioStore) -> AudioRotation:
    set_tenant(session, None, bypass=True)
    result = AudioRotation()
    rows = session.execute(
        select(AudioAsset.storage_key, ClinicalInteraction.status)
        .join(ClinicalInteraction, ClinicalInteraction.id == AudioAsset.interaction_id)
        .where(AudioAsset.storage_key.is_not(None), AudioAsset.deleted_at.is_(None))
        .order_by(AudioAsset.created_at)
    ).all()
    session.rollback()  # nothing is written to the database; do not hold a transaction open
    for key, status in rows:
        if key is None:
            continue
        if status != "ENDED":
            result.still_recording += 1
        elif not store.exists(key):
            result.missing += 1
        elif store.rewrap(key):
            result.reencrypted += 1
        else:
            result.already_current += 1
    return result
