import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, new_uuid


class CoverArrangement(Base):
    """One doctor asking a colleague to review their results for a short period (leave, a day off).

    It only widens whose results appear in the colleague's review list. It does not change who
    owns an encounter, an order or a prescription, and every review is still audited against the
    person who did it."""

    __tablename__ = "cover_arrangements"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    from_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    to_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
