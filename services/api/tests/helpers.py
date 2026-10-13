"""Shared builders for patient and scheduling tests."""

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from tests.conftest import make_staff

IST = ZoneInfo("Asia/Kolkata")
Headers = dict[str, str]


def tomorrow() -> date:
    return datetime.now(IST).date() + timedelta(days=1)


def make_facility(client: TestClient, admin: Headers, code: str = "MAIN") -> dict[str, Any]:
    r = client.post(
        "/api/v1/facilities", headers=admin, json={"name": f"Facility {code}", "code": code}
    )
    assert r.status_code == 201, r.text
    return r.json()


def make_practitioner(
    client: TestClient,
    admin: Headers,
    org: str,
    facility: dict[str, Any],
    email: str = "dr.rao@x.example.com",
) -> tuple[Headers, dict[str, Any]]:
    doctor_headers, user = make_staff(client, admin, email, "doctor", org)
    r = client.post(
        "/api/v1/practitioners",
        headers=admin,
        json={"user_id": user["id"], "facility_id": facility["id"], "specialty": "General Medicine",
              "consultation_minutes": 15},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    hours = [{"weekday": d, "start_time": "09:00:00", "end_time": "12:00:00"} for d in range(7)]
    r = client.put(
        f"/api/v1/practitioners/{r.json()['id']}/working-hours",
        headers=admin,
        json={"hours": hours},
    )
    assert r.status_code == 200, r.text
    return doctor_headers, r.json()


def make_patient(
    client: TestClient, headers: Headers, name: str = "Lakshmi Devi", **kw: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {"full_name": name, "age_years": 45, "administrative_gender": "female",
                            "mobile": "98765 43210", "confirm_not_duplicate": True, **kw}  # fmt: skip
    r = client.post("/api/v1/patients", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def slot(
    client: TestClient,
    headers: Headers,
    practitioner_id: str,
    index: int = 0,
    on: date | None = None,
) -> str:
    r = client.get(f"/api/v1/practitioners/{practitioner_id}/slots", headers=headers,
                   params={"on": (on or tomorrow()).isoformat()})  # fmt: skip
    assert r.status_code == 200, r.text
    return str(r.json()[index]["start_at"])


def reception(
    client: TestClient, admin: Headers, org: str, email: str = "recep@x.example.com"
) -> Headers:
    return make_staff(client, admin, email, "receptionist", org)[0]
