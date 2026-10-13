"""Database engine, base model and tenant-aware sessions.

Tenant context is carried on ``Session.info`` and pushed into Postgres as
transaction-local settings, which row-level security policies read. The
application must connect as a non-superuser, otherwise Postgres bypasses RLS.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, create_engine, event, func, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, SessionTransaction, mapped_column
from sqlalchemy.orm import sessionmaker as make_sessionmaker

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def create_db_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, future=True)


def create_sessionmaker(engine: Engine) -> "make_sessionmaker[Session]":
    return make_sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def set_tenant(
    session: Session,
    org_id: uuid.UUID | None,
    *,
    bypass: bool = False,
    platform: bool = False,
) -> None:
    """Set tenant context on the session and on the current transaction."""
    session.info.update(org_id=org_id, bypass=bypass, platform=platform)
    _push_context(session, session.connection())


def _push_context(session: Session, connection: Connection) -> None:
    info = session.info
    org = info.get("org_id")
    connection.execute(
        text(
            "select set_config('app.org_id', :org, true), "
            "set_config('app.bypass', :bypass, true), "
            "set_config('app.platform', :platform, true)"
        ),
        {
            "org": str(org) if org else "",
            "bypass": "on" if info.get("bypass") else "off",
            "platform": "on" if info.get("platform") else "off",
        },
    )


@event.listens_for(Session, "after_begin")
def _on_begin(session: Session, transaction: SessionTransaction, connection: Connection) -> None:
    _push_context(session, connection)
