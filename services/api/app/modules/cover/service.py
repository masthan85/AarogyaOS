"""Short-term cover between doctors, for results awaiting review."""

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import Conflict, NotFound
from app.modules.audit.service import record_audit
from app.modules.cover.models import CoverArrangement
from app.modules.identity.models import User
from app.modules.scheduling.models import Practitioner

MAX_DAYS = 31  # cover is for a break, not a permanent hand-over
CLINIC_TZ = ZoneInfo("Asia/Kolkata")


def today() -> date:
    return datetime.now(CLINIC_TZ).date()


class CoverIn(BaseModel):
    to_user_id: uuid.UUID
    starts_on: date
    ends_on: date

    @model_validator(mode="after")
    def _window(self) -> "CoverIn":
        if self.ends_on < self.starts_on:
            raise ValueError("The end date is before the start date")
        if (self.ends_on - self.starts_on).days >= MAX_DAYS:
            raise ValueError(f"Cover can last at most {MAX_DAYS} days")
        return self


class CoverOut(BaseModel):
    id: uuid.UUID
    from_user_id: uuid.UUID
    from_name: str
    to_user_id: uuid.UUID
    to_name: str
    starts_on: date
    ends_on: date
    active: bool


class Colleague(BaseModel):
    user_id: uuid.UUID
    name: str
    specialty: str


def _org(principal: Principal) -> uuid.UUID:
    assert principal.org_id is not None
    return principal.org_id


def colleagues(session: Session, principal: Principal) -> list[Colleague]:
    rows = session.execute(
        select(User.id, User.full_name, Practitioner.specialty)
        .join(Practitioner, Practitioner.user_id == User.id)
        .where(
            User.is_active.is_(True), Practitioner.status == "ACTIVE", User.id != principal.user_id
        )
        .order_by(User.full_name)
    ).all()
    return [Colleague(user_id=r[0], name=r[1], specialty=r[2]) for r in rows]


def _out(session: Session, rows: list[CoverArrangement]) -> list[CoverOut]:
    ids = {i for r in rows for i in (r.from_user_id, r.to_user_id)}
    names = (
        dict(session.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all())
        if ids
        else {}
    )
    now = today()
    return [
        CoverOut(
            id=r.id,
            from_user_id=r.from_user_id,
            from_name=names.get(r.from_user_id, "Unknown"),
            to_user_id=r.to_user_id,
            to_name=names.get(r.to_user_id, "Unknown"),
            starts_on=r.starts_on,
            ends_on=r.ends_on,
            active=r.revoked_at is None and r.starts_on <= now <= r.ends_on,
        )
        for r in rows
    ]


def create(session: Session, principal: Principal, body: CoverIn) -> CoverOut:
    if body.to_user_id == principal.user_id:
        raise Conflict("You cannot ask yourself to cover")
    if body.ends_on < today():
        raise Conflict("That period has already ended")
    if body.ends_on > today() + timedelta(days=366):
        raise Conflict("Cover can only be arranged up to a year ahead")
    ok = session.scalar(
        select(User.id)
        .join(Practitioner, Practitioner.user_id == User.id)
        .where(
            User.id == body.to_user_id, User.is_active.is_(True), Practitioner.status == "ACTIVE"
        )
    )
    if ok is None:
        raise NotFound("That doctor was not found")
    row = CoverArrangement(
        organisation_id=_org(principal),
        from_user_id=principal.user_id,
        to_user_id=body.to_user_id,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
    )
    session.add(row)
    session.flush()
    record_audit(
        session,
        principal.meta,
        org_id=_org(principal),
        actor_user_id=principal.user_id,
        action="COVER_ARRANGED",
        resource_type="cover_arrangements",
        resource_id=row.id,
        after={
            "to_user_id": str(body.to_user_id),
            "starts_on": str(body.starts_on),
            "ends_on": str(body.ends_on),
        },
    )
    session.commit()
    return _out(session, [row])[0]


def mine(session: Session, principal: Principal) -> list[CoverOut]:
    """Arrangements I made or that name me, recent first; ended ones stay listed for a month."""
    cutoff = today() - timedelta(days=30)
    rows = session.scalars(
        select(CoverArrangement)
        .where(
            (CoverArrangement.from_user_id == principal.user_id)
            | (CoverArrangement.to_user_id == principal.user_id),
            CoverArrangement.ends_on >= cutoff,
        )
        .order_by(CoverArrangement.starts_on.desc())
        .limit(50)
    ).all()
    return _out(session, list(rows))


def revoke(session: Session, principal: Principal, cover_id: uuid.UUID) -> CoverOut:
    row = session.get(CoverArrangement, cover_id)
    if row is None or principal.user_id not in (row.from_user_id, row.to_user_id):
        raise NotFound("Cover arrangement not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(CLINIC_TZ)
        record_audit(
            session,
            principal.meta,
            org_id=_org(principal),
            actor_user_id=principal.user_id,
            action="COVER_ENDED",
            resource_type="cover_arrangements",
            resource_id=row.id,
        )
    session.commit()
    return _out(session, [row])[0]


def covering_for(session: Session, user_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """Doctors whose results this user may review right now, mapped to their names."""
    now = today()
    ids = session.scalars(
        select(CoverArrangement.from_user_id).where(
            CoverArrangement.to_user_id == user_id,
            CoverArrangement.revoked_at.is_(None),
            CoverArrangement.starts_on <= now,
            CoverArrangement.ends_on >= now,
        )
    ).all()
    if not ids:
        return {}
    return dict(session.execute(select(User.id, User.full_name).where(User.id.in_(set(ids)))).all())
