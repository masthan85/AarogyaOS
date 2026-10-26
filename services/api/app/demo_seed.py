"""Demo data for trying the app on a development machine: `python -m app.cli demo-seed`.

Creates (once) an organisation "demo-clinic" with one user per role, a facility, a doctor profile
with working hours, recording and AI switched on, consent wording published, and an invented
patient. Every account uses the same published demo password, so this is for development only and
refuses to run in production. Nothing here is real: names, numbers and the patient are made up.
"""

import sys
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.db import create_db_engine, create_sessionmaker, set_tenant
from app.core.security import hash_password
from app.main import create_app
from app.modules.identity.models import Role, User, UserRole
from app.modules.identity.seed import sync_reference_data

PASSWORD = "Demo-pass-2026!"  # noqa: S105  (published on purpose; development only)
SLUG = "demo-clinic"
PLATFORM_EMAIL = "platform@demo.example.com"
API = "/api/v1"
STAFF = [
    ("doctor", "doctor@demo.example.com", "Dr Demo Doctor"),
    ("nurse", "nurse@demo.example.com", "Demo Nurse"),
    ("receptionist", "reception@demo.example.com", "Demo Receptionist"),
    ("pharmacist", "pharmacist@demo.example.com", "Demo Pharmacist"),
    ("lab_technician", "lab@demo.example.com", "Demo Lab Technician"),
]


def _ensure_platform_admin(settings: Settings) -> None:
    engine = create_db_engine(settings.database_url)
    try:
        with create_sessionmaker(engine)() as session:
            sync_reference_data(session)
            set_tenant(session, None, bypass=True)
            if session.scalar(
                select(User).where(User.organisation_id.is_(None), User.email == PLATFORM_EMAIL)
            ):
                return
            user = User(
                organisation_id=None,
                email=PLATFORM_EMAIL,
                full_name="Demo Platform Administrator",
                password_hash=hash_password(PASSWORD),
            )
            session.add(user)
            session.flush()
            role = session.scalar(select(Role).where(Role.key == "super_admin"))
            assert role is not None
            session.add(UserRole(user_id=user.id, role_id=role.id, organisation_id=None))
            session.commit()
    finally:
        engine.dispose()


def _login(client: TestClient, email: str, org: str | None) -> dict[str, str]:
    r = client.post(
        f"{API}/auth/login", json={"organisation_slug": org, "email": email, "password": PASSWORD}
    )
    if r.status_code != 200:
        raise SystemExit(
            f"Could not sign in as {email} ({r.status_code}). Was its password changed?"
        )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _ok(r: Any, what: str) -> Any:
    if r.status_code not in (200, 201):
        raise SystemExit(f"{what} failed: {r.status_code} {r.text[:300]}")
    return r.json()


def run(settings: Settings) -> int:
    if settings.environment == "production":
        print("Refusing to create demo accounts in production.")
        return 1
    _ensure_platform_admin(settings)
    with TestClient(create_app(settings)) as client:
        platform = _login(client, PLATFORM_EMAIL, None)
        exists = any(
            o["slug"] == SLUG
            for o in _ok(client.get(f"{API}/organisations", headers=platform), "List")
        )
        if exists:
            print(f"Organisation '{SLUG}' already exists; leaving it as it is.")
        else:
            _ok(
                client.post(
                    f"{API}/organisations",
                    headers=platform,
                    json={
                        "name": "Demo Clinic",
                        "slug": SLUG,
                        "admin_email": "admin@demo.example.com",
                        "admin_full_name": "Demo Administrator",
                        "admin_password": PASSWORD,
                    },
                ),
                "Create organisation",
            )
            admin = _login(client, "admin@demo.example.com", SLUG)
            facility = _ok(
                client.post(
                    f"{API}/facilities",
                    headers=admin,
                    json={"name": "Demo Clinic Main", "code": "MAIN"},
                ),
                "Create facility",
            )
            users: dict[str, Any] = {}
            for role, email, name in STAFF:
                users[role] = _ok(
                    client.post(
                        f"{API}/users",
                        headers=admin,
                        json={
                            "email": email,
                            "full_name": name,
                            "password": PASSWORD,
                            "roles": [role],
                        },
                    ),
                    f"Create {role}",
                )
            prac = _ok(
                client.post(
                    f"{API}/practitioners",
                    headers=admin,
                    json={
                        "user_id": users["doctor"]["id"],
                        "facility_id": facility["id"],
                        "specialty": "Neurosurgery",
                        "consultation_minutes": 15,
                    },
                ),
                "Create doctor profile",
            )
            hours = [
                {"weekday": d, "start_time": "09:00:00", "end_time": "17:00:00"} for d in range(7)
            ]
            _ok(
                client.put(
                    f"{API}/practitioners/{prac['id']}/working-hours",
                    headers=admin,
                    json={"hours": hours},
                ),
                "Set working hours",
            )
            _ok(
                client.put(
                    f"{API}/organisations/current/policy",
                    headers=admin,
                    json={"recording_enabled": True, "ai_processing_enabled": True},
                ),
                "Switch on recording and AI",
            )
            _ok(
                client.post(f"{API}/consent-policies/install-templates", headers=admin),
                "Consent wording",
            )
            reception = _login(client, "reception@demo.example.com", SLUG)
            _ok(
                client.post(
                    f"{API}/patients",
                    headers=reception,
                    json={
                        "full_name": "Demo Patient",
                        "age_years": 42,
                        "administrative_gender": "male",
                        "mobile": "9876543210",
                        "confirm_not_duplicate": True,
                    },
                ),
                "Register patient",
            )
            print("Demo organisation created.")
    print(f"\nSign in with organisation '{SLUG}' and password '{PASSWORD}':")
    print("  admin@demo.example.com  doctor@demo.example.com  nurse@demo.example.com")
    print("  reception@demo.example.com")
    print("  pharmacist@demo.example.com  lab@demo.example.com")
    print("These are demo accounts with a published password: never use them with real data.")
    return 0


def main() -> int:
    from app.core.config import get_settings

    return run(get_settings())


if __name__ == "__main__":
    sys.exit(main())
