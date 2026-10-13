from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.scheduling.models import Appointment
from tests.conftest import make_staff
from tests.helpers import make_facility, make_patient, make_practitioner, reception, slot, tomorrow

ORG = "alpha-clinic"
H = dict[str, str]


@pytest.fixture
def clinic(client: TestClient, org_a: H) -> dict[str, Any]:
    facility = make_facility(client, org_a)
    doctor, prac = make_practitioner(client, org_a, ORG, facility)
    return {
        "admin": org_a,
        "facility": facility,
        "doctor": doctor,
        "prac": prac,
        "recep": reception(client, org_a, ORG),
        "patient": None,
    }


def book(
    client: TestClient, c: dict[str, Any], patient: dict[str, Any], index: int = 0
) -> dict[str, Any]:
    start = slot(client, c["recep"], c["prac"]["id"], index)
    r = client.post(
        "/api/v1/appointments",
        headers=c["recep"],
        json={"patient_id": patient["id"], "practitioner_id": c["prac"]["id"], "start_at": start},
    )
    assert r.status_code == 201, r.text
    return r.json()


def insert_today(
    db: Session, c: dict[str, Any], patient: dict[str, Any], offset_hours: int = 0
) -> str:
    """A scheduled appointment starting now, inserted directly so check-in tests are time-independent."""
    org_id = db.execute(text("select id from organisations limit 1")).scalar_one()
    start = datetime.now(UTC) + timedelta(hours=offset_hours)
    a = Appointment(
        organisation_id=org_id,
        patient_id=patient["id"],
        practitioner_id=c["prac"]["id"],
        facility_id=c["facility"]["id"],
        start_at=start,
        end_at=start + timedelta(minutes=15),
        status="BOOKED",
    )
    db.add(a)
    db.commit()
    return str(a.id)


# ---- practitioners & slots -------------------------------------------------------


def test_practitioner_needs_a_doctor_user(
    client: TestClient, clinic: dict[str, Any], org_a: H
) -> None:
    nurse, user = make_staff(client, org_a, "n@alpha-clinic.example.com", "nurse", ORG)
    r = client.post(
        "/api/v1/practitioners",
        headers=org_a,
        json={"user_id": user["id"], "facility_id": clinic["facility"]["id"], "specialty": "ENT"},
    )
    assert r.status_code == 400
    again = client.post(
        "/api/v1/practitioners",
        headers=org_a,
        json={
            "user_id": clinic["prac"]["user_id"],
            "facility_id": clinic["facility"]["id"],
            "specialty": "ENT",
        },
    )
    assert again.status_code == 409


def test_overlapping_working_hours_rejected(client: TestClient, clinic: dict[str, Any]) -> None:
    hours = [
        {"weekday": 0, "start_time": "09:00:00", "end_time": "12:00:00"},
        {"weekday": 0, "start_time": "11:00:00", "end_time": "13:00:00"},
    ]
    r = client.put(
        f"/api/v1/practitioners/{clinic['prac']['id']}/working-hours",
        headers=clinic["admin"],
        json={"hours": hours},
    )
    assert r.status_code == 400
    bad = [{"weekday": 0, "start_time": "12:00:00", "end_time": "09:00:00"}]
    assert (
        client.put(
            f"/api/v1/practitioners/{clinic['prac']['id']}/working-hours",
            headers=clinic["admin"],
            json={"hours": bad},
        ).status_code
        == 422
    )


def test_slots_follow_working_hours_and_hide_taken_ones(
    client: TestClient, clinic: dict[str, Any]
) -> None:
    p = make_patient(client, clinic["recep"])
    url = f"/api/v1/practitioners/{clinic['prac']['id']}/slots"
    before = client.get(url, headers=clinic["recep"], params={"on": tomorrow().isoformat()}).json()
    assert len(before) == 12  # 09:00-12:00 in 15-minute slots
    assert before[0]["start_at"].endswith("03:30:00Z")  # 09:00 IST
    booked = book(client, clinic, p)
    after = client.get(url, headers=clinic["recep"], params={"on": tomorrow().isoformat()}).json()
    assert len(after) == 11 and booked["start_at"] not in [s["start_at"] for s in after]


def test_past_slots_are_never_offered(client: TestClient, clinic: dict[str, Any]) -> None:
    yesterday = (tomorrow() - timedelta(days=2)).isoformat()
    url = f"/api/v1/practitioners/{clinic['prac']['id']}/slots"
    assert client.get(url, headers=clinic["recep"], params={"on": yesterday}).json() == []


# ---- booking ---------------------------------------------------------------------


def test_booking_lifecycle_and_double_booking_protection(
    client: TestClient, clinic: dict[str, Any]
) -> None:
    p1, p2 = (
        make_patient(client, clinic["recep"]),
        make_patient(client, clinic["recep"], "Ravi Teja"),
    )
    appt = book(client, clinic, p1)
    assert appt["status"] == "BOOKED" and appt["patient_name"] == "Lakshmi Devi"
    assert appt["practitioner_name"] == "dr.rao"
    again = client.post(
        "/api/v1/appointments",
        headers=clinic["recep"],
        json={
            "patient_id": p2["id"],
            "practitioner_id": clinic["prac"]["id"],
            "start_at": appt["start_at"],
        },
    )
    assert again.status_code == 409


def test_off_grid_and_out_of_hours_times_rejected(
    client: TestClient, clinic: dict[str, Any]
) -> None:
    p = make_patient(client, clinic["recep"])
    start = datetime.fromisoformat(
        slot(client, clinic["recep"], clinic["prac"]["id"]).replace("Z", "+00:00")
    )
    for bad in (start + timedelta(minutes=5), start - timedelta(hours=8)):
        r = client.post(
            "/api/v1/appointments",
            headers=clinic["recep"],
            json={
                "patient_id": p["id"],
                "practitioner_id": clinic["prac"]["id"],
                "start_at": bad.isoformat(),
            },
        )
        assert r.status_code == 409, bad
    naive = client.post(
        "/api/v1/appointments",
        headers=clinic["recep"],
        json={
            "patient_id": p["id"],
            "practitioner_id": clinic["prac"]["id"],
            "start_at": "2030-01-01T09:00:00",
        },
    )
    assert naive.status_code == 422


def test_database_itself_refuses_overlapping_appointments(
    client: TestClient, clinic: dict[str, Any], db: Session
) -> None:
    """Defence against races: even if two requests pass the app check, Postgres says no."""
    p = make_patient(client, clinic["recep"])
    book(client, clinic, p)
    first = db.query(Appointment).one()
    dup = Appointment(
        organisation_id=first.organisation_id,
        patient_id=first.patient_id,
        practitioner_id=first.practitioner_id,
        facility_id=first.facility_id,
        start_at=first.start_at + timedelta(minutes=5),
        end_at=first.end_at + timedelta(minutes=5),
    )
    db.add(dup)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_patient_cannot_be_booked_with_two_doctors_at_once(
    client: TestClient, clinic: dict[str, Any], org_a: H
) -> None:
    doctor2, prac2 = make_practitioner(
        client, org_a, ORG, clinic["facility"], "dr.two@x.example.com"
    )
    p = make_patient(client, clinic["recep"])
    appt = book(client, clinic, p)
    r = client.post(
        "/api/v1/appointments",
        headers=clinic["recep"],
        json={"patient_id": p["id"], "practitioner_id": prac2["id"], "start_at": appt["start_at"]},
    )
    assert r.status_code == 409


def test_reschedule_frees_old_slot_and_cancel_frees_slot(
    client: TestClient, clinic: dict[str, Any]
) -> None:
    p = make_patient(client, clinic["recep"])
    appt = book(client, clinic, p, index=0)
    new_start = slot(client, clinic["recep"], clinic["prac"]["id"], index=3)
    r = client.post(
        f"/api/v1/appointments/{appt['id']}/reschedule",
        headers=clinic["recep"],
        json={"start_at": new_start},
    )
    assert r.status_code == 200
    assert datetime.fromisoformat(r.json()["start_at"]) == datetime.fromisoformat(new_start)
    offered = [
        s["start_at"]
        for s in client.get(
            f"/api/v1/practitioners/{clinic['prac']['id']}/slots",
            headers=clinic["recep"],
            params={"on": tomorrow().isoformat()},
        ).json()
    ]
    assert appt["start_at"] in offered and new_start not in offered
    c = client.post(
        f"/api/v1/appointments/{appt['id']}/cancel",
        headers=clinic["recep"],
        json={"reason": "Travelling"},
    )
    assert c.status_code == 200 and c.json()["status"] == "CANCELLED"
    assert new_start in [
        s["start_at"]
        for s in client.get(
            f"/api/v1/practitioners/{clinic['prac']['id']}/slots",
            headers=clinic["recep"],
            params={"on": tomorrow().isoformat()},
        ).json()
    ]


def test_invalid_state_transitions_are_refused(client: TestClient, clinic: dict[str, Any]) -> None:
    p = make_patient(client, clinic["recep"])
    appt = book(client, clinic, p)
    aid = appt["id"]
    r = clinic["recep"]
    assert (
        client.post(f"/api/v1/appointments/{aid}/confirm", headers=r).json()["status"]
        == "CONFIRMED"
    )
    assert (
        client.post(f"/api/v1/appointments/{aid}/no-show", headers=r).json()["status"] == "NO_SHOW"
    )
    for action in ("confirm", "cancel", "reschedule", "check-in"):
        body: dict[str, Any] = {"start_at": appt["start_at"]} if action == "reschedule" else {}
        assert (
            client.post(f"/api/v1/appointments/{aid}/{action}", headers=r, json=body).status_code
            == 409
        ), action


def test_tomorrows_appointment_cannot_be_checked_in_today(
    client: TestClient, clinic: dict[str, Any]
) -> None:
    appt = book(client, clinic, make_patient(client, clinic["recep"]))
    r = client.post(f"/api/v1/appointments/{appt['id']}/check-in", headers=clinic["recep"], json={})
    assert r.status_code == 409


# ---- check-in, walk-ins, queue ---------------------------------------------------


def test_check_in_issues_tokens_per_facility_per_day(
    client: TestClient, clinic: dict[str, Any], db: Session
) -> None:
    patients = [make_patient(client, clinic["recep"], n) for n in ("Asha Rani", "Ravi Teja")]
    tokens = []
    for p in patients:
        aid = insert_today(db, clinic, p, offset_hours=len(tokens))
        r = client.post(f"/api/v1/appointments/{aid}/check-in", headers=clinic["recep"], json={})
        assert r.status_code == 200, r.text
        tokens.append(r.json()["token_number"])
        assert r.json()["status"] == "WAITING"
    assert tokens == [1, 2]
    again = client.post(f"/api/v1/appointments/{aid}/check-in", headers=clinic["recep"], json={})
    assert again.status_code == 409  # already waiting


def test_walk_ins_queue_urgent_first_and_show_minimal_patient_data(
    client: TestClient, clinic: dict[str, Any]
) -> None:
    fid = clinic["facility"]["id"]
    a, b, c = (
        make_patient(client, clinic["recep"], n) for n in ("Asha Rani", "Ravi Teja", "Sita Devi")
    )
    for p, prio in ((a, "ROUTINE"), (b, "ROUTINE"), (c, "URGENT")):
        r = client.post(
            "/api/v1/walk-ins",
            headers=clinic["recep"],
            json={"patient_id": p["id"], "facility_id": fid, "priority": prio},
        )
        assert r.status_code == 201, r.text
    q = client.get("/api/v1/queue", headers=clinic["doctor"], params={"facility_id": fid}).json()
    assert [(i["patient_name"], i["token_number"]) for i in q] == [
        ("Sita Devi", 3),
        ("Asha Rani", 1),
        ("Ravi Teja", 2),
    ]
    assert "mobile" not in q[0] and "address" not in q[0]
    dup = client.post(
        "/api/v1/walk-ins",
        headers=clinic["recep"],
        json={"patient_id": a["id"], "facility_id": fid},
    )
    assert dup.status_code == 409


def test_doctor_calls_patient_one_consultation_at_a_time(
    client: TestClient, clinic: dict[str, Any]
) -> None:
    fid, prac = clinic["facility"]["id"], clinic["prac"]["id"]
    ids = []
    for n in ("Asha Rani", "Ravi Teja"):
        p = make_patient(client, clinic["recep"], n)
        ids.append(
            client.post(
                "/api/v1/walk-ins",
                headers=clinic["recep"],
                json={"patient_id": p["id"], "facility_id": fid, "practitioner_id": prac},
            ).json()["id"]
        )
    d = clinic["doctor"]

    def consult(appt_id: str) -> Any:
        return client.post(
            "/api/v1/encounters/consultation", headers=d, json={"appointment_id": appt_id}
        )

    first = consult(ids[0])
    assert first.status_code == 200 and first.json()["status"] == "IN_PROGRESS"
    assert consult(ids[1]).status_code == 409  # still with the first patient
    done = client.post(f"/api/v1/encounters/{first.json()['id']}/complete", headers=d)
    assert done.status_code == 200 and done.json()["status"] == "COMPLETED"
    assert consult(ids[1]).status_code == 200
    queue = client.get(
        "/api/v1/queue", headers=d, params={"facility_id": fid, "include_active": False}
    ).json()
    assert queue == []


def test_queue_is_scoped_to_the_selected_doctor(
    client: TestClient, clinic: dict[str, Any], org_a: H
) -> None:
    fid = clinic["facility"]["id"]
    _, prac2 = make_practitioner(client, org_a, ORG, clinic["facility"], "dr.two@x.example.com")
    p1, p2 = (
        make_patient(client, clinic["recep"], "Asha Rani"),
        make_patient(client, clinic["recep"], "Ravi Teja"),
    )
    for p, prac in ((p1, clinic["prac"]), (p2, prac2)):
        client.post(
            "/api/v1/walk-ins",
            headers=clinic["recep"],
            json={"patient_id": p["id"], "facility_id": fid, "practitioner_id": prac["id"]},
        )
    mine = client.get(
        "/api/v1/queue",
        headers=clinic["doctor"],
        params={"facility_id": fid, "practitioner_id": clinic["prac"]["id"]},
    ).json()
    assert [i["patient_name"] for i in mine] == ["Asha Rani"]


def test_scheduling_role_matrix(client: TestClient, clinic: dict[str, Any], org_a: H) -> None:
    p = make_patient(client, clinic["recep"])
    start = slot(client, clinic["recep"], clinic["prac"]["id"])
    booking = {"patient_id": p["id"], "practitioner_id": clinic["prac"]["id"], "start_at": start}
    nurse, _ = make_staff(client, org_a, "nurse@alpha-clinic.example.com", "nurse", ORG)
    billing, _ = make_staff(client, org_a, "bill@alpha-clinic.example.com", "billing_staff", ORG)
    # Clinicians cannot book; admins and billing cannot book or run the queue.
    for h in (clinic["doctor"], nurse, billing, org_a):
        assert client.post("/api/v1/appointments", headers=h, json=booking).status_code == 403
    assert (
        client.post(
            "/api/v1/walk-ins",
            headers=clinic["doctor"],
            json={"patient_id": p["id"], "facility_id": clinic["facility"]["id"]},
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/queue", headers=billing, params={"facility_id": clinic["facility"]["id"]}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/appointments", headers=billing).status_code == 200
    assert client.get("/api/v1/appointments", headers=org_a).status_code == 403
    # Only the doctor starts a consultation: reception and nurses are refused.
    walk = client.post(
        "/api/v1/walk-ins",
        headers=clinic["recep"],
        json={"patient_id": p["id"], "facility_id": clinic["facility"]["id"]},
    ).json()
    for h in (clinic["recep"], nurse, billing, org_a):
        r = client.post(
            "/api/v1/encounters/consultation", headers=h, json={"appointment_id": walk["id"]}
        )
        assert r.status_code == 403
    assert (
        client.post(
            "/api/v1/encounters/consultation",
            headers=clinic["doctor"],
            json={"appointment_id": walk["id"]},
        ).status_code
        == 200
    )
    # Only admins manage practitioners.
    assert (
        client.put(
            f"/api/v1/practitioners/{clinic['prac']['id']}/working-hours",
            headers=clinic["recep"],
            json={"hours": []},
        ).status_code
        == 403
    )


def test_timeline_records_the_journey_without_demographics(
    client: TestClient, clinic: dict[str, Any]
) -> None:
    p = make_patient(client, clinic["recep"])
    book(client, clinic, p)
    client.post(
        "/api/v1/walk-ins",
        headers=clinic["recep"],
        json={"patient_id": p["id"], "facility_id": clinic["facility"]["id"]},
    )
    events = client.get(f"/api/v1/patients/{p['id']}/timeline", headers=clinic["doctor"]).json()
    kinds = [e["event_type"] for e in events]
    assert set(kinds) == {"PATIENT_REGISTERED", "APPOINTMENT_BOOKED", "PATIENT_CHECKED_IN"}
    assert kinds[-1] == "PATIENT_REGISTERED"  # newest first
    assert "Lakshmi" not in str(events)


def test_scheduling_is_tenant_isolated(
    client: TestClient, clinic: dict[str, Any], org_b: H
) -> None:
    p = make_patient(client, clinic["recep"])
    appt = book(client, clinic, p)
    rb = reception(client, org_b, "beta-hospital", "r@beta.example.com")
    assert client.get("/api/v1/appointments", headers=rb).json() == []
    assert (
        client.post(f"/api/v1/appointments/{appt['id']}/cancel", headers=rb, json={}).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/practitioners/{clinic['prac']['id']}/slots",
            headers=rb,
            params={"on": tomorrow().isoformat()},
        ).status_code
        == 404
    )
    fb = make_facility(client, org_b, "B1")
    assert (
        client.get(
            "/api/v1/queue", headers=rb, params={"facility_id": clinic["facility"]["id"]}
        ).status_code
        == 404
    )
    assert client.get("/api/v1/queue", headers=rb, params={"facility_id": fb["id"]}).json() == []
    assert (
        client.post(
            "/api/v1/appointments",
            headers=rb,
            json={
                "patient_id": p["id"],
                "practitioner_id": clinic["prac"]["id"],
                "start_at": appt["start_at"],
            },
        ).status_code
        == 404
    )


def test_concurrent_bookings_of_one_slot_have_exactly_one_winner(
    client: TestClient, clinic: dict[str, Any]
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    patients = [
        make_patient(client, clinic["recep"], n)
        for n in ("Asha Rani", "Ravi Teja", "Sita Devi", "Gopal Rao")
    ]
    start = slot(client, clinic["recep"], clinic["prac"]["id"])

    def attempt(p: dict[str, Any]) -> int:
        return client.post(
            "/api/v1/appointments",
            headers=clinic["recep"],
            json={
                "patient_id": p["id"],
                "practitioner_id": clinic["prac"]["id"],
                "start_at": start,
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = sorted(pool.map(attempt, patients))
    assert codes == [201, 409, 409, 409]
