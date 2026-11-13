"""Organisation allowances for speech and AI, counted per calendar month (UTC).

An allowance protects a clinic from an unexpected bill. Reaching one switches off new recordings or
new model calls for the rest of the month and nothing else: every screen still works by hand, and a
recording already under way is not cut off. Counts come from the usage tables the product already
keeps, which hold durations and token counts but no clinical content.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.modules.ai.models import AiUsage
from app.modules.interactions.models import SpeechUsage
from app.modules.tenancy.policy import OrgPolicy

State = Literal["UNLIMITED", "OK", "NEAR", "REACHED"]


class UsageLimitReached(Conflict):
    code = "usage_limit_reached"


class Allowance(BaseModel):
    used: float
    limit: int | None
    state: State


class UsagePosition(BaseModel):
    month_start: datetime
    alert_percent: int
    speech_minutes: Allowance
    ai_calls: Allowance


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _state(used: float, limit: int | None, alert_percent: int) -> State:
    if limit is None:
        return "UNLIMITED"
    if used >= limit:
        return "REACHED"
    return "NEAR" if used * 100 >= limit * alert_percent else "OK"


def speech_minutes_used(session: Session, org_id: uuid.UUID) -> float:
    seconds = session.scalar(
        select(func.coalesce(func.sum(SpeechUsage.audio_seconds), 0)).where(
            SpeechUsage.organisation_id == org_id, SpeechUsage.created_at >= month_start()
        )
    )
    return round(float(seconds or 0) / 60, 1)


def ai_calls_used(session: Session, org_id: uuid.UUID) -> int:
    # Every attempt counts, including failures: a failed call may still have been charged for.
    return int(
        session.scalar(
            select(func.count())
            .select_from(AiUsage)
            .where(AiUsage.organisation_id == org_id, AiUsage.created_at >= month_start())
        )
        or 0
    )


def position(session: Session, org_id: uuid.UUID, policy: OrgPolicy) -> UsagePosition:
    speech, calls = speech_minutes_used(session, org_id), ai_calls_used(session, org_id)
    alert = policy.usage_alert_percent
    return UsagePosition(
        month_start=month_start(),
        alert_percent=alert,
        speech_minutes=Allowance(
            used=speech,
            limit=policy.monthly_speech_minutes_limit,
            state=_state(speech, policy.monthly_speech_minutes_limit, alert),
        ),
        ai_calls=Allowance(
            used=calls,
            limit=policy.monthly_ai_calls_limit,
            state=_state(calls, policy.monthly_ai_calls_limit, alert),
        ),
    )


def ai_reached(session: Session, org_id: uuid.UUID, policy: OrgPolicy) -> bool:
    limit = policy.monthly_ai_calls_limit
    return limit is not None and ai_calls_used(session, org_id) >= limit


def check_speech(session: Session, org_id: uuid.UUID, policy: OrgPolicy) -> None:
    limit = policy.monthly_speech_minutes_limit
    if limit is not None and speech_minutes_used(session, org_id) >= limit:
        raise UsageLimitReached(
            "This month's speech allowance is used up, so recording is off. "
            "The visit can be documented by hand; an administrator can raise the allowance."
        )


def check_ai(session: Session, org_id: uuid.UUID, policy: OrgPolicy) -> None:
    if ai_reached(session, org_id, policy):
        raise UsageLimitReached(
            "This month's AI allowance is used up, so software assistance is off. "
            "The visit can be documented by hand; an administrator can raise the allowance."
        )
