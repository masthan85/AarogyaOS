"""Small, honest load test over real TCP: a clinic's mixed traffic.

    AAROGYA_DATABASE_URL=... python -m app.cli seed
    uvicorn app.main:create_app --factory --port 8765 --workers 2 &
    AAROGYA_DATABASE_URL=... python scripts/loadtest.py http://127.0.0.1:8765 [users] [seconds]

Creates a throwaway organisation (development database only) and runs
`users` concurrent staff for `seconds`, each looping through: search patients, open a chart,
read the clinical state, record vitals, add a note. Reports throughput and latency percentiles.

What it does NOT tell you: results depend entirely on the machine, the database and the network, so
numbers from a laptop or a CI runner say nothing about production. Use it to compare before/after on
the same hardware and to find regressions, and run a real test against a production-like stack.
"""

import asyncio
import random
import sys
import time
import uuid
from collections import defaultdict

import httpx

sys.path.insert(0, ".")
from app.core.config import get_settings  # noqa: E402
from app.core.db import create_db_engine, create_sessionmaker, set_tenant  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.modules.identity.models import Role, User, UserRole  # noqa: E402
from tests.clinical_helpers import API, post  # noqa: E402
from tests.conftest import PASSWORD, make_staff  # noqa: E402
from tests.helpers import make_facility, make_patient, make_practitioner, reception  # noqa: E402


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * p))] if s else 0.0


def provision(base: str) -> tuple[dict[str, str], dict[str, str], str, str]:
    slug = f"load-{uuid.uuid4().hex[:8]}"
    sm = create_sessionmaker(create_db_engine(get_settings().database_url))
    with sm() as db:
        set_tenant(db, None, bypass=True)
        root = User(
            organisation_id=None,
            email=f"{slug}@platform.example.com",
            full_name="Root",
            password_hash=hash_password(PASSWORD),
        )
        db.add(root)
        db.flush()
        role = db.query(Role).filter_by(key="super_admin").one()
        db.add(UserRole(user_id=root.id, role_id=role.id, organisation_id=None))
        db.commit()
    with httpx.Client(base_url=base, timeout=30) as c:

        def login(email: str, org: str | None) -> dict[str, str]:
            r = c.post(
                "/api/v1/auth/login",
                json={"organisation_slug": org, "email": email, "password": PASSWORD},
            )
            r.raise_for_status()
            return {"Authorization": f"Bearer {r.json()['access_token']}"}

        platform = login(f"{slug}@platform.example.com", None)
        c.post(
            "/api/v1/organisations",
            headers=platform,
            json={
                "name": "Load",
                "slug": slug,
                "admin_email": f"admin@{slug}.example.com",
                "admin_full_name": "Admin",
                "admin_password": PASSWORD,
            },
        ).raise_for_status()
        admin = login(f"admin@{slug}.example.com", slug)
        facility = make_facility(c, admin)
        doctor, prac = make_practitioner(c, admin, slug, facility)
        nurse, _ = make_staff(c, admin, f"nurse@{slug}.example.com", "nurse", slug)
        recep = reception(c, admin, slug)
        patient = make_patient(c, recep, "Lakshmi Devi", age_years=45)
        walk = post(
            c,
            recep,
            "/walk-ins",
            {
                "patient_id": patient["id"],
                "facility_id": facility["id"],
                "practitioner_id": prac["id"],
            },
        )
        appt = walk.json()["id"]
        enc = post(c, nurse, "/encounters/triage", {"appointment_id": appt}).json()["id"]
        post(c, doctor, "/encounters/consultation", {"appointment_id": appt}).raise_for_status()
        return nurse, doctor, patient["id"], enc


async def worker(
    base: str,
    nurse: dict[str, str],
    doctor: dict[str, str],
    pid: str,
    enc: str,
    stop: float,
    stats: dict[str, list[float]],
    errors: dict[str, int],
) -> None:
    async with httpx.AsyncClient(base_url=base, timeout=30) as c:

        async def call(
            name: str, method: str, url: str, headers: dict[str, str], **kw: object
        ) -> None:
            t = time.perf_counter()
            try:
                r = await c.request(method, f"{API}{url}", headers=headers, **kw)  # type: ignore[arg-type]
                ok = r.status_code < 400
            except httpx.HTTPError:
                ok = False
            stats[name].append((time.perf_counter() - t) * 1000)
            if not ok:
                errors[name] += 1

        while time.perf_counter() < stop:
            await call("search", "GET", "/patients/search", doctor, params={"name": "Lakshmi"})
            await call("chart", "GET", f"/patients/{pid}", doctor)
            await call("clinical_state", "GET", f"/patients/{pid}/clinical-state", doctor)
            await call(
                "vitals",
                "POST",
                f"/encounters/{enc}/vitals",
                nurse,
                json={"heart_rate": random.randint(60, 110)},  # noqa: S311
            )
            await call(
                "note",
                "POST",
                f"/encounters/{enc}/notes",
                doctor,
                json={"note_type": "GENERAL", "content": "load test note"},
            )


async def main(base: str, users: int, seconds: int) -> None:
    nurse, doctor, pid, enc = provision(base)
    stats: dict[str, list[float]] = defaultdict(list)
    errors: dict[str, int] = defaultdict(int)
    stop = time.perf_counter() + seconds
    t0 = time.perf_counter()
    await asyncio.gather(
        *(worker(base, nurse, doctor, pid, enc, stop, stats, errors) for _ in range(users))
    )
    elapsed = time.perf_counter() - t0
    total = sum(len(v) for v in stats.values())
    print(
        f"{users} concurrent users, {elapsed:.0f}s, {total} requests, {total / elapsed:.1f} req/s"
    )
    print(f"{'operation':16}{'n':>7}{'err':>6}{'p50 ms':>9}{'p95 ms':>9}{'p99 ms':>9}")
    for name, values in stats.items():
        row = (len(values), errors[name], pct(values, 0.5), pct(values, 0.95), pct(values, 0.99))
        print(f"{name:16}{row[0]:7}{row[1]:6}{row[2]:9.1f}{row[3]:9.1f}{row[4]:9.1f}")


if __name__ == "__main__":
    asyncio.run(
        main(
            sys.argv[1],
            int(sys.argv[2]) if len(sys.argv) > 2 else 10,
            int(sys.argv[3]) if len(sys.argv) > 3 else 20,
        )
    )
