"""Releases upgrade a database that already holds a clinic's data. This builds a separate database at
an older revision, puts rows in it, upgrades to the latest, and checks the rows survived. It then
takes the newest, reversible migrations back down and up again, so a rollback of the last release is
known to work. Earlier migrations are not all reversible and are not claimed to be."""

import os
import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from tests.conftest import ADMIN_URL, APP_PASSWORD, APP_ROLE

DB = "aarogya_migration_test"
OLD = "0012"  # a release from before billing extras, seals, MFA, idempotency and the visit rule
REVERSIBLE_FROM = "0015"


@pytest.fixture
def old_database(app_url: str) -> Iterator[str]:
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"drop database if exists {DB} with (force)"))
        conn.execute(text(f"create database {DB} owner {APP_ROLE}"))
    url = (
        make_url(ADMIN_URL)
        .set(database=DB, username=APP_ROLE, password=APP_PASSWORD)
        .render_as_string(hide_password=False)
    )
    previous = os.environ.get("ALEMBIC_DATABASE_URL")
    os.environ["ALEMBIC_DATABASE_URL"] = url
    try:
        yield url
    finally:
        if previous is None:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL"] = previous
        with admin.connect() as conn:
            conn.execute(text(f"drop database if exists {DB} with (force)"))
        admin.dispose()


def _revision(url: str) -> str:
    engine = create_engine(url)
    with engine.connect() as conn:
        rev = str(conn.execute(text("select version_num from alembic_version")).scalar())
    engine.dispose()
    return rev


def test_an_old_database_with_data_upgrades_and_the_latest_release_can_be_rolled_back(
    old_database: str,
) -> None:
    cfg = Config("alembic.ini")
    command.upgrade(cfg, OLD)
    assert _revision(old_database) == OLD

    org, facility = uuid.uuid4(), uuid.uuid4()
    engine = create_engine(old_database)
    with engine.begin() as conn:
        # Row-level security applies to this role too; maintenance writes declare the bypass.
        conn.execute(text("select set_config('app.bypass', 'on', true)"))
        conn.execute(
            text(
                "insert into organisations (id, name, slug, status, settings) "
                "values (:id, 'Old Clinic', 'old-clinic', 'ACTIVE', '{\"policy\": {}}')"
            ),
            {"id": org},
        )
        conn.execute(
            text(
                "insert into facilities (id, organisation_id, name, code, kind, timezone, status) "
                "values (:id, :org, 'Main', 'MAIN', 'CLINIC', 'Asia/Kolkata', 'ACTIVE')"
            ),
            {"id": facility, "org": org},
        )

    command.upgrade(cfg, "head")
    head = _revision(old_database)
    assert head != OLD

    def check_data_and_new_rules() -> None:
        with engine.begin() as conn:
            conn.execute(text("select set_config('app.bypass', 'on', true)"))
            name = conn.execute(text("select name from organisations where id = :id"), {"id": org})
            assert name.scalar() == "Old Clinic"
            kept = conn.execute(
                text("select code from facilities where id = :id"), {"id": facility}
            )
            assert kept.scalar() == "MAIN"
            columns = {
                r[0]
                for r in conn.execute(
                    text(
                        "select column_name from information_schema.columns "
                        "where table_name = 'idempotency_keys'"
                    )
                )
            }
            assert {"key", "scope", "resource_id"} <= columns
            index = conn.execute(
                text(
                    "select 1 from pg_indexes where indexname = 'uq_appointments_one_active_visit'"
                )
            )
            assert index.scalar() == 1

    check_data_and_new_rules()

    # Roll the most recent releases back and forward again, with the data in place.
    command.downgrade(cfg, REVERSIBLE_FROM)
    assert _revision(old_database) == REVERSIBLE_FROM
    with engine.begin() as conn:
        gone = conn.execute(text("select to_regclass('idempotency_keys')")).scalar()
        assert gone is None
    command.upgrade(cfg, "head")
    assert _revision(old_database) == head
    check_data_and_new_rules()
    engine.dispose()
