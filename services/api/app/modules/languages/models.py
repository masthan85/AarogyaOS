from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Language(Base):
    """Language support is data. Adding a language is a row, not a code change."""

    __tablename__ = "languages"

    tag: Mapped[str] = mapped_column(String(35), primary_key=True)  # BCP-47, e.g. te-IN
    name: Mapped[str] = mapped_column(String(80))
    native_name: Mapped[str] = mapped_column(String(80))
    script: Mapped[str] = mapped_column(String(20))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Per-provider support as measured/declared, e.g. {"development": "synthetic-only"}.
    provider_support: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
