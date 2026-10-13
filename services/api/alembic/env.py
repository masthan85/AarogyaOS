import os

from alembic import context
from sqlalchemy import create_engine

import app.modules.ai.models
import app.modules.audit.models
import app.modules.clinical.models
import app.modules.consent.models
import app.modules.identity.models
import app.modules.interactions.models
import app.modules.languages.models
import app.modules.patients.models
import app.modules.scheduling.models
import app.modules.summaries.models
import app.modules.tenancy.models  # noqa: F401  (register tables)
from app.core.config import get_settings
from app.core.db import Base

target_metadata = Base.metadata


def _url() -> str:
    return os.environ.get("ALEMBIC_DATABASE_URL") or get_settings().database_url


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
