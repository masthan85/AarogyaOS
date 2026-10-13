import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.db import set_tenant
from tests.conftest import make_staff


def _facility(client: TestClient, headers: dict[str, str], code: str) -> dict[str, str]:
    r = client.post(
        "/api/v1/facilities", headers=headers, json={"name": f"Fac {code}", "code": code}
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_lists_never_cross_organisations(
    client: TestClient, org_a: dict[str, str], org_b: dict[str, str]
) -> None:
    fa = _facility(client, org_a, "A1")
    fb = _facility(client, org_b, "B1")
    make_staff(client, org_a, "nurse@alpha-clinic.example.com", "nurse", "alpha-clinic")

    assert [f["id"] for f in client.get("/api/v1/facilities", headers=org_a).json()] == [fa["id"]]
    assert [f["id"] for f in client.get("/api/v1/facilities", headers=org_b).json()] == [fb["id"]]
    emails_b = {u["email"] for u in client.get("/api/v1/users", headers=org_b).json()}
    assert emails_b == {"admin@beta-hospital.example.com"}
    actors_a = {x["actor_user_id"] for x in client.get("/api/v1/audit-logs", headers=org_a).json()}
    ids_b = {u["id"] for u in client.get("/api/v1/users", headers=org_b).json()}
    assert not actors_a & ids_b


def test_direct_id_access_across_tenants_is_404(
    client: TestClient, org_a: dict[str, str], org_b: dict[str, str]
) -> None:
    fb = _facility(client, org_b, "B1")
    user_b = client.get("/api/v1/users", headers=org_b).json()[0]
    assert client.get(f"/api/v1/facilities/{fb['id']}", headers=org_a).status_code == 404
    assert (
        client.patch(
            f"/api/v1/facilities/{fb['id']}", headers=org_a, json={"name": "pwned"}
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/users/{user_b['id']}", headers=org_a).status_code == 404
    assert client.post(f"/api/v1/users/{user_b['id']}/deactivate", headers=org_a).status_code == 404
    assert (
        client.put(
            f"/api/v1/users/{user_b['id']}/roles", headers=org_a, json={"roles": ["doctor"]}
        ).status_code
        == 404
    )
    # B is untouched
    assert client.get(f"/api/v1/facilities/{fb['id']}", headers=org_b).json()["name"] == "Fac B1"
    assert client.get(f"/api/v1/users/{user_b['id']}", headers=org_b).json()["is_active"] is True


def test_cannot_attach_department_to_another_tenants_facility(
    client: TestClient, org_a: dict[str, str], org_b: dict[str, str]
) -> None:
    fb = _facility(client, org_b, "B1")
    r = client.post(
        "/api/v1/departments", headers=org_a, json={"facility_id": fb["id"], "name": "Cardiology"}
    )
    assert r.status_code == 404
    assert client.get("/api/v1/departments", headers=org_b).json() == []


def test_same_facility_code_allowed_in_different_orgs(
    client: TestClient, org_a: dict[str, str], org_b: dict[str, str]
) -> None:
    _facility(client, org_a, "MAIN")
    _facility(client, org_b, "MAIN")
    dup = client.post("/api/v1/facilities", headers=org_a, json={"name": "x", "code": "MAIN"})
    assert dup.status_code == 409


# ---- Database-level isolation (RLS), independent of application filters -------------


def _org_ids(client: TestClient, db: Session) -> tuple[uuid.UUID, uuid.UUID]:
    rows = db.execute(text("select id from organisations order by slug")).scalars().all()
    return rows[0], rows[1]


def test_rls_restricts_unfiltered_queries(
    client: TestClient, db: Session, org_a: dict[str, str], org_b: dict[str, str]
) -> None:
    _facility(client, org_a, "A1")
    _facility(client, org_b, "B1")
    a, b = _org_ids(client, db)
    app = client.app.state.sessionmaker  # type: ignore[attr-defined]
    with app() as s:
        set_tenant(s, a)
        rows = s.execute(text("select organisation_id from facilities")).scalars().all()
        assert rows == [a]
        assert s.execute(text("select count(*) from users")).scalar() == 1
        assert (
            s.execute(
                text("select count(*) from audit_logs where organisation_id = :b"), {"b": b}
            ).scalar()
            == 0
        )


def test_rls_fails_closed_without_tenant_context(
    client: TestClient, db: Session, org_a: dict[str, str]
) -> None:
    _facility(client, org_a, "A1")
    app = client.app.state.sessionmaker  # type: ignore[attr-defined]
    with app() as s:
        for table in ("facilities", "users", "audit_logs", "organisations", "refresh_tokens"):
            assert s.execute(text(f"select count(*) from {table}")).scalar() == 0, table


def test_rls_blocks_writing_into_another_tenant(
    client: TestClient, db: Session, org_a: dict[str, str], org_b: dict[str, str]
) -> None:
    a, b = _org_ids(client, db)
    app = client.app.state.sessionmaker  # type: ignore[attr-defined]
    with app() as s:
        set_tenant(s, a)
        with pytest.raises(DBAPIError):
            s.execute(
                text(
                    "insert into facilities (id, organisation_id, name, code, kind, timezone, status)"
                    " values (gen_random_uuid(), :b, 'x', 'X', 'CLINIC', 'Asia/Kolkata', 'ACTIVE')"
                ),
                {"b": b},
            )
