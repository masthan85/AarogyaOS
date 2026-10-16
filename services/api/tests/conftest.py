"""Test harness. Needs a Postgres superuser URL (AAROGYA_TEST_ADMIN_URL) to create an
isolated database and a NON-superuser role, because superusers bypass row-level security.
"""

import contextlib
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import set_tenant
from app.core.security import hash_password
from app.main import create_app
from app.modules.identity.models import Role, User, UserRole
from app.modules.identity.seed import sync_reference_data

ADMIN_URL = os.environ.get(
    "AAROGYA_TEST_ADMIN_URL", "postgresql+psycopg://postgres@localhost:5432/postgres"
)
TEST_DB = "aarogya_test"
APP_ROLE = "aarogya_test_app"
APP_PASSWORD = "aarogya_test_app"  # noqa: S105
PASSWORD = "correct-horse-battery"  # noqa: S105
TENANT_TABLES = (
    "ai_suggestion_actions, ai_suggestions, ai_candidates, ai_extractions, ai_usage, "
    "knowledge_chunks, knowledge_documents, patient_summaries, dispensings, note_templates, cover_arrangements, "
    "speech_usage, audio_assets, transcript_corrections, transcript_segments, interaction_speakers, clinical_interactions, "
    "consents, consent_policies, "
    "follow_ups, investigation_results, service_requests, prescription_items, prescriptions, "
    "patient_medications, allergies, conditions, clinical_notes, observations, encounters, "
    "queue_entries, queue_counters, working_hours, appointments, practitioners, "
    "patient_revisions, patient_languages, patient_identifiers, patients, mrn_counters, "
    "audit_logs, clinical_events, refresh_tokens, user_roles, users, departments, "
    "facilities, organisations"
)


@pytest.fixture(scope="session")
def app_url() -> str:
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"drop database if exists {TEST_DB} with (force)"))
        exists = conn.execute(
            text("select 1 from pg_roles where rolname = :r"), {"r": APP_ROLE}
        ).scalar()
        if not exists:
            conn.execute(
                text(f"create role {APP_ROLE} login password '{APP_PASSWORD}' nosuperuser")
            )
        conn.execute(text(f"create database {TEST_DB} owner {APP_ROLE}"))
    # Optional: exercise the pgvector path when the server ships the extension.
    ext = create_engine(
        make_url(ADMIN_URL).set(database=TEST_DB).render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    with ext.connect() as conn:
        with contextlib.suppress(Exception):  # the extension may not be installed here
            conn.execute(text("create extension if not exists vector"))
    ext.dispose()
    admin.dispose()
    url = (
        make_url(ADMIN_URL)
        .set(database=TEST_DB, username=APP_ROLE, password=APP_PASSWORD)
        .render_as_string(hide_password=False)
    )
    os.environ["ALEMBIC_DATABASE_URL"] = url
    command.upgrade(Config("alembic.ini"), "head")
    return url


@pytest.fixture(scope="session")
def superuser_engine(app_url: str) -> Iterator[Engine]:
    url = make_url(ADMIN_URL).set(database=TEST_DB).render_as_string(hide_password=False)
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_db(app_url: str, superuser_engine: Engine) -> Iterator[None]:
    with superuser_engine.connect() as conn:
        conn.execute(text(f"truncate {TENANT_TABLES} cascade"))
    yield


@pytest.fixture
def settings(app_url: str, tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=app_url,
        jwt_secret="test-secret-test-secret-test-secret-123",
        max_failed_logins=3,
        speech_provider="development",
        speech_monitor_interval_seconds=0.05,
        audio_store_path=str(tmp_path / "audio"),
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as c:
        with app.state.sessionmaker() as session:
            sync_reference_data(session)
        yield c
    app.state.engine.dispose()


@pytest.fixture
def db(client: TestClient) -> Iterator[Session]:
    with client.app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        set_tenant(session, None, bypass=True)
        yield session


def login(client: TestClient, email: str, password: str = PASSWORD, org: str | None = None):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/v1/auth/login",
        json={"organisation_slug": org, "email": email, "password": password},
    )


def auth(
    client: TestClient, email: str, org: str | None, password: str = PASSWORD
) -> dict[str, str]:
    r = login(client, email, password, org)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def platform_headers(client: TestClient, db: Session) -> dict[str, str]:
    user = User(
        organisation_id=None,
        email="root@platform.example.com",
        full_name="Root",
        password_hash=hash_password(PASSWORD),
    )
    db.add(user)
    db.flush()
    role = db.query(Role).filter_by(key="super_admin").one()
    db.add(UserRole(user_id=user.id, role_id=role.id, organisation_id=None))
    db.commit()
    return auth(client, "root@platform.example.com", None)


def make_org(client: TestClient, platform_headers: dict[str, str], slug: str) -> dict[str, str]:
    """Create an organisation via the API; returns admin auth headers."""
    r = client.post(
        "/api/v1/organisations",
        headers=platform_headers,
        json={
            "name": f"Org {slug}",
            "slug": slug,
            "admin_email": f"admin@{slug}.example.com",
            "admin_full_name": "Admin",
            "admin_password": PASSWORD,
        },
    )
    assert r.status_code == 201, r.text
    return auth(client, f"admin@{slug}.example.com", slug)


def make_staff(client: TestClient, admin: dict[str, str], email: str, role: str, org: str):  # type: ignore[no-untyped-def]
    r = client.post(
        "/api/v1/users",
        headers=admin,
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "password": PASSWORD,
            "roles": [role],
        },
    )
    assert r.status_code == 201, r.text
    return auth(client, email, org), r.json()


@pytest.fixture
def org_a(client: TestClient, platform_headers: dict[str, str]) -> dict[str, str]:
    return make_org(client, platform_headers, "alpha-clinic")


@pytest.fixture
def org_b(client: TestClient, platform_headers: dict[str, str]) -> dict[str, str]:
    return make_org(client, platform_headers, "beta-hospital")


def new_id() -> str:
    return str(uuid.uuid4())
