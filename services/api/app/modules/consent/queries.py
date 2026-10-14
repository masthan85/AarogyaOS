"""Read-only consent rules. Imported by the recording code; contains no side effects.

A consent is active when the patient's NEWEST decision for that purpose is a grant that has not
expired, and any consent it depends on is active too. Recording consent never implies any other
purpose: each is checked on its own.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.consent.models import PURPOSES, Consent, ConsentPolicy

# Withdrawing the parent switches the dependent purpose off as well.
DEPENDS_ON: dict[str, str] = {
    "AUDIO_RETENTION": "AUDIO_RECORDING",
    "AI_PROCESSING": "SPEECH_TRANSCRIPTION",
}


def latest_consent(session: Session, patient_id: uuid.UUID, purpose: str) -> Consent | None:
    return session.scalars(
        select(Consent)
        .where(Consent.patient_id == patient_id, Consent.purpose == purpose)
        .order_by(Consent.granted_at.desc(), Consent.id)
        .limit(1)
    ).first()


def _live(consent: Consent | None, now: datetime) -> bool:
    if consent is None or consent.status != "GRANTED":
        return False
    return consent.expires_at is None or consent.expires_at > now


def active_consent(
    session: Session, patient_id: uuid.UUID, purpose: str, now: datetime | None = None
) -> Consent | None:
    now = now or datetime.now(UTC)
    own = latest_consent(session, patient_id, purpose)
    if not _live(own, now):
        return None
    parent = DEPENDS_ON.get(purpose)
    if parent and active_consent(session, patient_id, parent, now) is None:
        return None
    return own


def missing_consents(session: Session, patient_id: uuid.UUID, required: list[str]) -> list[str]:
    return [p for p in required if active_consent(session, patient_id, p) is None]


def current_policy(session: Session, purpose: str, language: str) -> ConsentPolicy | None:
    """Newest ACTIVE wording for a purpose, in the requested language or else English."""
    for lang in (language, "en-IN"):
        policy = session.scalars(
            select(ConsentPolicy)
            .where(
                ConsentPolicy.purpose == purpose,
                ConsentPolicy.language == lang,
                ConsentPolicy.status == "ACTIVE",
            )
            .order_by(ConsentPolicy.version.desc())
            .limit(1)
        ).first()
        if policy:
            return policy
    return None


def purposes() -> tuple[str, ...]:
    return PURPOSES
