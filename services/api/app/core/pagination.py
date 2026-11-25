"""Keyset pagination for lists that only grow, newest first.

A page is asked for with `before`, the id of the last row the caller already has. The next page is
the rows strictly older than that one, ordered by (timestamp, id) so rows written in the same
instant are neither skipped nor repeated, however many rows arrive while someone is reading. The
response body stays a plain list: the caller passes the last id it received to get the next page,
and an empty or short page means it has reached the end."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, tuple_
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.core.errors import AppError


def newest_first[T](
    session: Session,
    stmt: Select[T],
    model: type[Any],
    at: InstrumentedAttribute[datetime],
    before: uuid.UUID | None,
) -> Select[T]:
    """Order `stmt` newest first and, given `before`, start after that row."""
    stmt = stmt.order_by(at.desc(), model.id.desc())
    if before is None:
        return stmt
    # Row-level security applies here too, so another organisation's id is simply not found.
    anchor = session.get(model, before)
    if anchor is None:
        raise AppError("The row to page from was not found.", code="invalid_cursor")
    return stmt.where(tuple_(at, model.id) < tuple_(getattr(anchor, at.key), anchor.id))
