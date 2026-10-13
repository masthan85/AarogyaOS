"""End-to-end smoke test over real TCP: consent, recording session, audio, transcript.

Unlike the pytest suite (which uses Starlette's in-process client), this talks to a running server,
so it exercises uvicorn's real WebSocket stack. Usage:

    AAROGYA_DATABASE_URL=... python -m app.cli seed
    uvicorn app.main:create_app --factory --port 8765 &
    AAROGYA_DATABASE_URL=... python scripts/smoke_recording.py http://127.0.0.1:8765

Creates a throwaway organisation. Development database only.
"""

import json
import sys
import uuid

import httpx
from websockets.sync.client import connect

sys.path.insert(0, ".")
from app.core.config import get_settings  # noqa: E402
from app.core.db import create_db_engine, create_sessionmaker, set_tenant  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.modules.identity.models import Role, User, UserRole  # noqa: E402
from tests.clinical_helpers import Visit, get, post  # noqa: E402
from tests.conftest import PASSWORD  # noqa: E402
from tests.helpers import make_facility, make_patient, make_practitioner, reception  # noqa: E402
from tests.speech_helpers import SECOND, enable_recording, grant, install_wording, token_of  # noqa: E402


def login(c: httpx.Client, email: str, org: str | None) -> dict[str, str]:
    r = c.post(
        "/api/v1/auth/login", json={"organisation_slug": org, "email": email, "password": PASSWORD}
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def main(base: str) -> None:
    slug = f"smoke-{uuid.uuid4().hex[:8]}"
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
        db.add(
            UserRole(
                user_id=root.id,
                role_id=db.query(Role).filter_by(key="super_admin").one().id,
                organisation_id=None,
            )
        )
        db.commit()
    with httpx.Client(base_url=base, timeout=20) as c:
        platform = login(c, f"{slug}@platform.example.com", None)
        r = c.post(
            "/api/v1/organisations",
            headers=platform,
            json={
                "name": "Smoke",
                "slug": slug,
                "admin_email": f"admin@{slug}.example.com",
                "admin_full_name": "Admin",
                "admin_password": PASSWORD,
            },
        )
        r.raise_for_status()
        admin = login(c, f"admin@{slug}.example.com", slug)
        facility = make_facility(c, admin)
        doctor, prac = make_practitioner(c, admin, slug, facility)
        recep = reception(c, admin, slug)
        from tests.conftest import make_staff

        nurse, _ = make_staff(c, admin, "nurse@x.example.com", "nurse", slug)
        patient = make_patient(c, recep)
        walk = post(
            c,
            recep,
            "/walk-ins",
            {
                "patient_id": patient["id"],
                "facility_id": facility["id"],
                "practitioner_id": prac["id"],
            },
        ).json()
        post(c, nurse, "/encounters/triage", {"appointment_id": walk["id"]})
        enc = post(c, doctor, "/encounters/consultation", {"appointment_id": walk["id"]}).json()
        enable_recording(c, admin)
        install_wording(c, admin)
        grant(c, recep, patient["id"], "AUDIO_RECORDING", "SPEECH_TRANSCRIPTION")
        v = Visit(admin, facility, doctor, prac, nurse, recep, patient, walk["id"], enc["id"])

        ia = post(
            c,
            doctor,
            "/interactions",
            {
                "patient_id": patient["id"],
                "purpose": "CONSULTATION",
                "encounter_id": v.enc_id,
                "language_hint": "te-IN",
            },
        ).json()
        start = post(c, doctor, f"/interactions/{ia['id']}/start").json()
        ws_url = base.replace("http", "ws") + start["gateway_path"]
        with connect(ws_url) as ws:
            ws.send(json.dumps({"type": "auth", "token": token_of(doctor)}))
            print("server:", json.loads(ws.recv()))
            for _ in range(6):
                ws.send(SECOND)
            ws.send(json.dumps({"type": "stop"}))
            try:
                while True:
                    print("server:", ws.recv())
            except Exception as exc:  # connection closed by server
                print("closed:", type(exc).__name__)
        t = get(c, doctor, f"/interactions/{ia['id']}/transcript").json()
        print("status:", t["status"], "segments:", len(t["segments"]))
        for s in t["segments"]:
            print(
                f"  [{s['seq']}] {s['speaker_id']} ({s['language']}+{s['secondary_language']}): "
                f"{s['raw_text']}"
            )
        assert t["status"] == "ENDED" and len(t["segments"]) == 2, "smoke test failed"
        print("OK")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765")
