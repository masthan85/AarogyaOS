"""Idempotency keys: a repeated request with the same key is answered without being done twice.

Clinics work on poor networks. A phone that sends "record payment", loses the reply and sends it
again must not record two payments. The client attaches an `Idempotency-Key` header; the first
request claims the key in the same transaction as its write, and a repeat finds the key taken and
is answered with the current state instead.

The key row holds no request or response content, only who used which key for what, so nothing
clinical or financial is copied here.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import Header
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.context import Principal
from app.core.db import Base, new_uuid
from app.core.errors import AppError


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("organisation_id", "user_id", "scope", "key", name="uq_idempotency_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column()
    scope: Mapped[str] = mapped_column(String(80))
    key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


Key = Annotated[str | None, Header(alias="Idempotency-Key", min_length=8, max_length=100)]


def claim(session: Session, principal: Principal, scope: str, key: str | None) -> bool:
    """True if this request should do the work; False if the same key already did it.

    The claim is part of the caller's transaction: if the write fails and rolls back, the key is
    free again. Two identical requests racing each other queue on the unique index, so exactly one
    proceeds.
    """
    if key is None:
        return True
    if principal.org_id is None:
        raise AppError("Idempotency keys need an organisation")
    inserted = session.execute(
        insert(IdempotencyKey)
        .values(
            id=new_uuid(),
            organisation_id=principal.org_id,
            user_id=principal.user_id,
            scope=scope,
            key=key,
        )
        .on_conflict_do_nothing(constraint="uq_idempotency_key")
        .returning(IdempotencyKey.id)
    ).first()
    return inserted is not None
