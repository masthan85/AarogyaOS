import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.context import RequestMeta
from app.core.db import set_tenant
from app.core.security import hash_password, verify_password
from app.modules.audit.models import ClinicalEvent
from app.modules.audit.service import emit_event
from tests.conftest import PASSWORD, make_staff


def test_audit_never_contains_passwords_or_tokens(
    client: TestClient, org_a: dict[str, str]
) -> None:
    make_staff(client, org_a, "dr@alpha-clinic.example.com", "doctor", "alpha-clinic")
    body = client.get("/api/v1/audit-logs", headers=org_a).text
    assert PASSWORD not in body and "refresh_token" not in body and "password" not in body.lower()


def test_audit_rows_carry_request_context(client: TestClient, org_a: dict[str, str]) -> None:
    client.post(
        "/api/v1/facilities",
        headers={**org_a, "X-Request-ID": "corr-123"},
        json={"name": "Main", "code": "MAIN"},
    )
    log = client.get(
        "/api/v1/audit-logs", headers=org_a, params={"action": "FACILITY_CREATED"}
    ).json()[0]
    assert log["correlation_id"] == "corr-123"


def test_event_outbox_is_tenant_scoped(
    client: TestClient, db: Session, org_a: dict[str, str], org_b: dict[str, str]
) -> None:
    a, b = db.execute(text("select id from organisations order by slug")).scalars().all()
    with client.app.state.sessionmaker() as s:  # type: ignore[attr-defined]
        set_tenant(s, a)
        emit_event(
            s,
            org_id=a,
            event_type="PATIENT_REGISTERED",
            aggregate_type="patient",
            aggregate_id=uuid.uuid4(),
            payload={"facility": "A1"},
        )
        s.commit()
    with client.app.state.sessionmaker() as s:  # type: ignore[attr-defined]
        set_tenant(s, b)
        assert s.scalars(select(ClinicalEvent)).all() == []
        set_tenant(s, a)
        assert len(s.scalars(select(ClinicalEvent)).all()) == 1


def test_password_hashing() -> None:
    h = hash_password(PASSWORD)
    assert h != PASSWORD and h.startswith("$argon2id$")
    assert verify_password(PASSWORD, h) and not verify_password("other", h)
    assert not verify_password(PASSWORD, None)


def test_production_rejects_default_secret() -> None:
    with pytest.raises(ValueError):
        Settings(environment="production")
    Settings(
        environment="production",
        jwt_secret="x" * 40,
        field_encryption_key="azRrazRrazRrazRrazRrazRrazRrazRrazRrazRrazA=",
        database_url="postgresql+psycopg://aarogya_app:not-the-dev-password@db/aarogya",
    )


def test_health_endpoints_and_error_shape(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready", "migrations": "ok"}
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401 and r.json()["status"] == 401 and "correlation_id" in r.json()
    assert r.headers["X-Request-ID"]


def test_request_meta_is_plain_data() -> None:
    assert RequestMeta(None, None, "c").correlation_id == "c"
