"""Builders for clinical tests: a checked-in patient with the full care team."""

from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import make_staff
from tests.helpers import Headers, make_facility, make_patient, make_practitioner, reception

ORG = "alpha-clinic"
API = "/api/v1"


@dataclass
class Visit:
    admin: Headers
    facility: dict[str, Any]
    doctor: Headers
    prac: dict[str, Any]
    nurse: Headers
    recep: Headers
    patient: dict[str, Any]
    appt_id: str
    enc_id: str = ""


def make_visit(
    client: TestClient,
    admin: Headers,
    *,
    age: int = 45,
    stage: str = "triage",
    name: str = "Lakshmi Devi",
) -> Visit:
    """stage: 'triage' (nurse has opened the encounter) or 'consult' (doctor has taken over)."""
    facility = make_facility(client, admin)
    doctor, prac = make_practitioner(client, admin, ORG, facility)
    nurse, _ = make_staff(client, admin, "nurse@alpha-clinic.example.com", "nurse", ORG)
    recep = reception(client, admin, ORG)
    patient = make_patient(client, recep, name, age_years=age)
    walk = client.post(
        f"{API}/walk-ins",
        headers=recep,
        json={
            "patient_id": patient["id"],
            "facility_id": facility["id"],
            "practitioner_id": prac["id"],
        },
    )
    assert walk.status_code == 201, walk.text
    v = Visit(admin, facility, doctor, prac, nurse, recep, patient, walk.json()["id"])
    r = client.post(f"{API}/encounters/triage", headers=nurse, json={"appointment_id": v.appt_id})
    assert r.status_code == 201, r.text
    v.enc_id = r.json()["id"]
    if stage == "consult":
        r = client.post(
            f"{API}/encounters/consultation", headers=doctor, json={"appointment_id": v.appt_id}
        )
        assert r.status_code == 200, r.text
    return v


def post(client: TestClient, h: Headers, url: str, body: dict[str, Any] | None = None) -> Any:
    return client.post(f"{API}{url}", headers=h, json=body or {})


def get(client: TestClient, h: Headers, url: str, **params: Any) -> Any:
    return client.get(f"{API}{url}", headers=h, params=params)


def rx_body(*names: str, route: str = "ORAL") -> dict[str, Any]:
    return {
        "items": [
            {
                "medicine_name": n,
                "dose": "1 tablet",
                "route": route,
                "frequency": "twice daily",
                "duration_days": 5,
            }
            for n in names
        ]
    }


def record_nka(client: TestClient, v: Visit) -> None:
    r = post(client, v.doctor, f"/encounters/{v.enc_id}/allergies", {"is_nka": True})
    assert r.status_code == 201, r.text
