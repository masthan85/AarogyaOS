from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from tests.clinical_helpers import API, Visit, get, make_visit, post, record_nka, rx_body
from tests.conftest import make_staff
from tests.helpers import make_patient, slot

H = dict[str, str]


@pytest.fixture
def visit(client: TestClient, org_a: H) -> Visit:
    return make_visit(client, org_a)


@pytest.fixture
def consult(client: TestClient, org_a: H) -> Visit:
    return make_visit(client, org_a, stage="consult")


# ---- starting the visit ------------------------------------------------------------


def test_triage_is_idempotent_and_needs_a_checked_in_patient(
    client: TestClient, visit: Visit
) -> None:
    again = post(client, visit.nurse, "/encounters/triage", {"appointment_id": visit.appt_id})
    assert again.status_code == 200 and again.json()["id"] == visit.enc_id
    assert again.json()["status"] == "TRIAGE"
    # A patient who is booked but has not arrived cannot be triaged.
    booked_patient = make_patient(client, visit.recep, "Ravi Teja", mobile="9123456780")
    booked = post(client, visit.recep, "/appointments", {
        "patient_id": booked_patient["id"], "practitioner_id": visit.prac["id"],
        "start_at": slot(client, visit.recep, visit.prac["id"]),
    })  # fmt: skip
    assert booked.status_code == 201
    not_arrived = post(
        client, visit.nurse, "/encounters/triage", {"appointment_id": booked.json()["id"]}
    )
    assert not_arrived.status_code == 409


def test_only_the_right_roles_start_triage_or_consultation(
    client: TestClient, visit: Visit
) -> None:
    body = {"appointment_id": visit.appt_id}
    for h in (visit.doctor, visit.recep, visit.admin):
        assert post(client, h, "/encounters/triage", body).status_code == 403
    for h in (visit.nurse, visit.recep, visit.admin):
        assert post(client, h, "/encounters/consultation", body).status_code == 403


def test_consultation_takes_over_the_triage_encounter(client: TestClient, visit: Visit) -> None:
    r = post(client, visit.doctor, "/encounters/consultation", {"appointment_id": visit.appt_id})
    assert (
        r.status_code == 200
        and r.json()["id"] == visit.enc_id
        and r.json()["status"] == "IN_PROGRESS"
    )
    q = get(client, visit.doctor, "/queue", facility_id=visit.facility["id"]).json()
    assert q[0]["status"] == "IN_CONSULTATION" and q[0]["encounter_status"] == "IN_PROGRESS"
    # Reopening the app and tapping again does not create a second encounter.
    assert (
        post(
            client, visit.doctor, "/encounters/consultation", {"appointment_id": visit.appt_id}
        ).json()["id"]
        == visit.enc_id
    )


def test_a_doctor_cannot_take_another_doctors_patient(
    client: TestClient, visit: Visit, org_a: H
) -> None:
    other, _ = make_staff(
        client, org_a, "dr.other@alpha-clinic.example.com", "doctor", "alpha-clinic"
    )
    # no practitioner profile
    assert (
        post(
            client, other, "/encounters/consultation", {"appointment_id": visit.appt_id}
        ).status_code
        == 409
    )
    from tests.helpers import make_practitioner

    other2, _ = make_practitioner(
        client, org_a, "alpha-clinic", visit.facility, "dr.third@x.example.com"
    )
    assert (
        post(
            client, other2, "/encounters/consultation", {"appointment_id": visit.appt_id}
        ).status_code
        == 403
    )


def test_encounter_must_be_in_the_callers_organisation(
    client: TestClient, visit: Visit, org_b: H
) -> None:
    assert (
        get(client, org_b, f"/encounters/{visit.enc_id}").status_code == 403
    )  # admin has no clinical access
    nurse_b, _ = make_staff(client, org_b, "n@beta.example.com", "nurse", "beta-hospital")
    assert get(client, nurse_b, f"/encounters/{visit.enc_id}").status_code == 404
    assert (
        post(client, nurse_b, f"/encounters/{visit.enc_id}/vitals", {"heart_rate": 80}).status_code
        == 404
    )
    assert (
        get(client, nurse_b, f"/patients/{visit.patient['id']}/clinical-state").status_code == 404
    )


# ---- vitals ------------------------------------------------------------------------


def test_vitals_convert_fahrenheit_flag_abnormal_and_keep_the_original(
    client: TestClient, visit: Visit
) -> None:
    r = post(client, visit.nurse, f"/encounters/{visit.enc_id}/vitals", {
        "temperature": {"value": 101.5, "unit": "F"}, "systolic_bp": 150, "diastolic_bp": 95,
        "heart_rate": 88, "spo2": 92, "height_cm": 160, "weight_kg": 64})  # fmt: skip
    assert r.status_code == 201, r.text
    by = {o["code"]: o for o in r.json()}
    assert by["TEMPERATURE_C"]["value"] == "38.61" and by["TEMPERATURE_C"]["original_unit"] == "°F"
    assert by["TEMPERATURE_C"]["interpretation"] == "HIGH"
    assert (
        by["SYSTOLIC_BP"]["interpretation"] == "HIGH"
        and by["DIASTOLIC_BP"]["interpretation"] == "HIGH"
    )
    assert by["HEART_RATE"]["interpretation"] == "NORMAL" and by["SPO2"]["interpretation"] == "LOW"
    assert by["HEIGHT_CM"]["interpretation"] == "NOT_APPLICABLE"
    assert by["SPO2"]["reference_version"].startswith("default-adult")
    # Entered by a nurse: staff-entered and not yet verified.
    assert (
        by["HEART_RATE"]["source"] == "STAFF_ENTERED"
        and by["HEART_RATE"]["verification_state"] == "UNVERIFIED"
    )


def test_implausible_or_inconsistent_vitals_are_rejected(client: TestClient, visit: Visit) -> None:
    url = f"/encounters/{visit.enc_id}/vitals"
    assert (
        post(client, visit.nurse, url, {"temperature": {"value": 380, "unit": "C"}}).status_code
        == 400
    )
    assert post(client, visit.nurse, url, {"heart_rate": 900}).status_code == 400
    assert post(client, visit.nurse, url, {"spo2": 101}).status_code == 400
    assert (
        post(client, visit.nurse, url, {"systolic_bp": 80, "diastolic_bp": 90}).status_code == 400
    )
    assert post(client, visit.nurse, url, {"systolic_bp": 120}).status_code == 422
    assert post(client, visit.nurse, url, {}).status_code == 422
    assert (
        post(client, visit.nurse, url, {"temperature": {"value": 98, "unit": "K"}}).status_code
        == 400
    )


def test_children_get_no_adult_interpretation(client: TestClient, org_a: H) -> None:
    v = make_visit(client, org_a, age=6, name="Baby Kumar")
    r = post(
        client,
        v.nurse,
        f"/encounters/{v.enc_id}/vitals",
        {"heart_rate": 200, "temperature": {"value": 39, "unit": "C"}},
    )
    assert {o["interpretation"] for o in r.json()} == {"UNKNOWN"}
    state = get(client, v.doctor, f"/patients/{v.patient['id']}/clinical-state").json()
    assert any(a["code"] == "PAEDIATRIC_RANGES" for a in state["alerts"])


def test_vital_correction_supersedes_and_preserves_history(
    client: TestClient, visit: Visit, superuser_engine: Engine
) -> None:
    first = post(
        client, visit.nurse, f"/encounters/{visit.enc_id}/vitals", {"heart_rate": 180}
    ).json()[0]
    fixed = client.put(f"{API}/observations/{first['id']}", headers=visit.nurse, json={"value": 80})
    assert fixed.status_code == 200 and fixed.json()["supersedes_id"] == first["id"]
    assert fixed.json()["interpretation"] == "NORMAL"
    assert fixed.json()["verification_state"] == "CLINICIAN_EDITED"
    again = client.put(f"{API}/observations/{first['id']}", headers=visit.nurse, json={"value": 70})
    assert again.status_code == 409  # already replaced
    with superuser_engine.connect() as conn:
        rows = conn.execute(
            text("select value, is_current from observations order by recorded_at")
        ).all()
    assert [(float(r[0]), r[1]) for r in rows] == [(180.0, False), (80.0, True)]
    detail = get(client, visit.doctor, f"/encounters/{visit.enc_id}").json()
    assert [float(v["value"]) for v in detail["vitals"]] == [80.0]


# ---- notes -------------------------------------------------------------------------


def test_note_permissions_by_type_and_ownership(
    client: TestClient, consult: Visit, org_a: H
) -> None:
    url = f"/encounters/{consult.enc_id}/notes"
    assert (
        post(
            client, consult.nurse, url, {"note_type": "CHIEF_COMPLAINT", "content": "Fever 2 days"}
        ).status_code
        == 201
    )
    assert (
        post(client, consult.nurse, url, {"note_type": "EXAMINATION", "content": "x"}).status_code
        == 403
    )
    assert (
        post(
            client, consult.doctor, url, {"note_type": "EXAMINATION", "content": "Chest clear"}
        ).status_code
        == 201
    )
    from tests.helpers import make_practitioner

    other, _ = make_practitioner(
        client, org_a, "alpha-clinic", consult.facility, "dr.other@x.example.com"
    )
    assert post(client, other, url, {"note_type": "ASSESSMENT", "content": "x"}).status_code == 403
    assert (
        post(client, consult.doctor, url, {"note_type": "HPI", "content": "   "}).status_code == 422
    )
    assert (
        post(
            client,
            consult.doctor,
            url,
            {"note_type": "HPI", "content": "x", "source": "AI_EXTRACTED"},
        ).status_code
        == 422
    )


def test_patient_reported_source_survives_a_doctor_typing_it(
    client: TestClient, consult: Visit
) -> None:
    r = post(client, consult.doctor, f"/encounters/{consult.enc_id}/notes",
             {"note_type": "HPI", "content": "Says pain worse at night", "source": "PATIENT_REPORTED"})  # fmt: skip
    assert (
        r.json()["source"] == "PATIENT_REPORTED"
        and r.json()["verification_state"] == "CLINICIAN_CONFIRMED"
    )


def test_note_edit_creates_new_version(client: TestClient, consult: Visit) -> None:
    n = post(
        client,
        consult.doctor,
        f"/encounters/{consult.enc_id}/notes",
        {"note_type": "PLAN", "content": "Rest"},
    ).json()
    e = client.put(
        f"{API}/notes/{n['id']}", headers=consult.doctor, json={"content": "Rest and fluids"}
    )
    assert e.status_code == 200 and e.json()["supersedes_id"] == n["id"]
    notes = get(client, consult.doctor, f"/encounters/{consult.enc_id}").json()["notes"]
    assert [x["content"] for x in notes] == ["Rest and fluids"]


# ---- allergies, conditions, verification ------------------------------------------


def test_a_possible_allergy_is_never_recorded_as_confirmed(
    client: TestClient, visit: Visit
) -> None:
    r = post(client, visit.nurse, f"/encounters/{visit.enc_id}/allergies", {
        "substance": "Penicillin", "certainty": "POSSIBLE", "source": "PATIENT_REPORTED",
        "reaction": "Rash as a child"})  # fmt: skip
    a = r.json()
    assert r.status_code == 201 and a["certainty"] == "POSSIBLE"
    assert a["source"] == "PATIENT_REPORTED" and a["verification_state"] == "UNVERIFIED"
    alerts = get(client, visit.doctor, f"/patients/{visit.patient['id']}/clinical-state").json()[
        "alerts"
    ]
    msg = next(x["message"] for x in alerts if x["code"] == "ALLERGY")
    assert "penicillin" in msg.lower() and "possible" in msg and "not yet verified" in msg


def test_no_known_allergies_rules(client: TestClient, visit: Visit) -> None:
    url = f"/encounters/{visit.enc_id}/allergies"

    def state() -> Any:
        return get(client, visit.doctor, f"/patients/{visit.patient['id']}/clinical-state").json()

    assert any(a["code"] == "ALLERGY_STATUS_UNKNOWN" for a in state()["alerts"])
    assert post(client, visit.nurse, url, {"is_nka": True}).status_code == 201
    s = state()
    assert s["allergy_status_recorded"] and not any(
        a["code"].startswith("ALLERGY") for a in s["alerts"]
    )
    # Recording a real allergy retires the 'none known' statement instead of contradicting it.
    assert (
        post(
            client, visit.nurse, url, {"substance": "Sulfa drugs", "severity": "SEVERE"}
        ).status_code
        == 201
    )
    names = [a["substance"] for a in state()["allergies"]]
    assert names == ["Sulfa drugs"]
    assert post(client, visit.nurse, url, {"is_nka": True}).status_code == 400
    assert post(client, visit.nurse, url, {"substance": ""}).status_code == 422


def test_verification_confirm_reject_and_rejected_facts_leave_the_state(
    client: TestClient, visit: Visit
) -> None:
    a = post(
        client,
        visit.nurse,
        f"/encounters/{visit.enc_id}/allergies",
        {"substance": "Peanuts", "category": "FOOD"},
    ).json()
    ok = post(client, visit.doctor, f"/clinical/allergies/{a['id']}/verify", {"action": "confirm"})
    assert ok.json()["verification_state"] == "CLINICIAN_CONFIRMED"
    assert (
        post(
            client, visit.doctor, f"/clinical/allergies/{a['id']}/verify", {"action": "reject"}
        ).status_code
        == 400
    )
    rej = post(
        client,
        visit.doctor,
        f"/clinical/allergies/{a['id']}/verify",
        {"action": "reject", "reason": "Patient mistaken"},
    )
    assert rej.json()["verification_state"] == "CLINICIAN_REJECTED"
    state = get(client, visit.doctor, f"/patients/{visit.patient['id']}/clinical-state").json()
    assert state["allergies"] == []
    assert (
        post(
            client, visit.doctor, f"/clinical/bogus/{a['id']}/verify", {"action": "confirm"}
        ).status_code
        == 404
    )
    assert (
        post(
            client, visit.recep, f"/clinical/allergies/{a['id']}/verify", {"action": "confirm"}
        ).status_code
        == 403
    )


def test_only_a_doctor_records_and_confirms_diagnoses(client: TestClient, consult: Visit) -> None:
    url = f"/encounters/{consult.enc_id}/conditions"
    assert post(client, consult.nurse, url, {"display": "Viral fever"}).status_code == 403
    c = post(client, consult.doctor, url, {"display": "Viral fever"}).json()
    assert c["certainty"] == "PROVISIONAL" and c["verification_state"] == "CLINICIAN_CONFIRMED"
    assert (
        client.put(
            f"{API}/conditions/{c['id']}", headers=consult.nurse, json={"certainty": "CONFIRMED"}
        ).status_code
        == 403
    )
    confirmed = client.put(
        f"{API}/conditions/{c['id']}", headers=consult.doctor, json={"certainty": "CONFIRMED"}
    )
    assert confirmed.status_code == 200 and confirmed.json()["certainty"] == "CONFIRMED"
    kinds = [
        e["event_type"]
        for e in get(client, consult.doctor, f"/patients/{consult.patient['id']}/timeline").json()
    ]
    assert kinds.count("DIAGNOSIS_CONFIRMED") == 1


def test_codes_must_come_with_a_system(client: TestClient, consult: Visit) -> None:
    r = post(
        client,
        consult.doctor,
        f"/encounters/{consult.enc_id}/conditions",
        {"display": "Fever", "code": "R50.9"},
    )
    assert r.status_code == 422
    ok = post(
        client,
        consult.doctor,
        f"/encounters/{consult.enc_id}/conditions",
        {"display": "Fever", "code": "R50.9", "code_system": "ICD-10"},
    )
    assert ok.status_code == 201


# ---- aggregated state & alerts -----------------------------------------------------


def test_clinical_state_aggregates_and_ranks_alerts(client: TestClient, consult: Visit) -> None:
    pid, enc = consult.patient["id"], consult.enc_id
    post(
        client,
        consult.nurse,
        f"/encounters/{enc}/vitals",
        {
            "temperature": {"value": 41, "unit": "C"},
            "heart_rate": 90,
            "height_cm": 170,
            "weight_kg": 70,
        },
    )
    post(
        client,
        consult.nurse,
        f"/encounters/{enc}/allergies",
        {"substance": "Aspirin", "severity": "SEVERE"},
    )
    post(
        client,
        consult.doctor,
        f"/encounters/{enc}/conditions",
        {"display": "Type 2 diabetes", "category": "PROBLEM", "certainty": "CONFIRMED"},
    )
    post(
        client,
        consult.nurse,
        f"/encounters/{enc}/medications",
        {
            "name": "Metformin 500 mg",
            "generic_name": "metformin",
            "dose": "500 mg",
            "frequency": "BD",
        },
    )
    s = get(client, consult.doctor, f"/patients/{pid}/clinical-state").json()
    assert s["bmi"] == 24.2
    assert [c["display"] for c in s["conditions"]] == ["Type 2 diabetes"]
    assert [m["name"] for m in s["medications"]] == ["Metformin 500 mg"]
    assert s["alerts"][0]["level"] == "CRITICAL" and "temperature" in s["alerts"][0]["message"]
    assert {a["code"] for a in s["alerts"]} >= {"CRITICAL_VITAL", "ALLERGY"}
    assert [e["status"] for e in s["recent_encounters"]] == ["IN_PROGRESS"]
    audit = get(client, consult.admin, "/audit-logs", action="CLINICAL_STATE_VIEWED").json()
    assert len(audit) == 1


def test_clinical_state_role_matrix(client: TestClient, consult: Visit, org_a: H) -> None:
    url = f"/patients/{consult.patient['id']}/clinical-state"
    assert get(client, consult.nurse, url).status_code == 200
    lab, _ = make_staff(
        client, org_a, "lab@alpha-clinic.example.com", "lab_technician", "alpha-clinic"
    )
    bill, _ = make_staff(
        client, org_a, "bill@alpha-clinic.example.com", "billing_staff", "alpha-clinic"
    )
    ph, _ = make_staff(client, org_a, "ph@alpha-clinic.example.com", "pharmacist", "alpha-clinic")
    for h in (consult.recep, consult.admin, lab, bill, ph):
        assert get(client, h, url).status_code == 403


# ---- completion --------------------------------------------------------------------


def test_complete_requires_resolved_drafts_then_locks_the_visit(
    client: TestClient, consult: Visit
) -> None:
    enc = consult.enc_id
    record_nka(client, consult)
    rx = post(
        client, consult.doctor, f"/encounters/{enc}/prescriptions", rx_body("Paracetamol 500 mg")
    ).json()
    order = post(
        client, consult.doctor, f"/encounters/{enc}/orders", {"category": "LAB", "name": "CBC"}
    ).json()
    blocked = post(client, consult.doctor, f"/encounters/{enc}/complete")
    assert blocked.status_code == 409 and "1 prescription" in blocked.json()["detail"]
    post(client, consult.doctor, f"/prescriptions/{rx['id']}/sign")
    assert (
        post(client, consult.doctor, f"/encounters/{enc}/complete").status_code == 409
    )  # order still draft
    assert post(client, consult.doctor, f"/orders/{order['id']}/place").status_code == 200
    done = post(client, consult.doctor, f"/encounters/{enc}/complete")
    assert done.status_code == 200 and done.json()["ended_at"]
    appt = get(client, consult.recep, "/appointments", patient_id=consult.patient["id"]).json()[0]
    assert appt["status"] == "COMPLETED"
    # The closed visit refuses further clinical writes.
    for url, body in (
        (f"/encounters/{enc}/vitals", {"heart_rate": 80}),
        (f"/encounters/{enc}/notes", {"note_type": "PLAN", "content": "x"}),
        (f"/encounters/{enc}/allergies", {"substance": "Dust"}),
        (f"/encounters/{enc}/follow-ups", {"due_date": "2999-01-01", "reason": "Review"}),
    ):
        assert post(client, consult.doctor, url, body).status_code == 409, url
    assert post(client, consult.doctor, f"/encounters/{enc}/complete").status_code == 409


def test_only_the_owning_doctor_completes(client: TestClient, consult: Visit, org_a: H) -> None:
    from tests.helpers import make_practitioner

    other, _ = make_practitioner(
        client, org_a, "alpha-clinic", consult.facility, "dr.other@x.example.com"
    )
    assert post(client, other, f"/encounters/{consult.enc_id}/complete").status_code == 403
    assert post(client, consult.nurse, f"/encounters/{consult.enc_id}/complete").status_code == 403


# ---- the database refuses to rewrite history ---------------------------------------


def test_database_blocks_editing_or_deleting_clinical_facts(
    client: TestClient, consult: Visit, superuser_engine: Engine, db: Any
) -> None:
    post(client, consult.nurse, f"/encounters/{consult.enc_id}/vitals", {"heart_rate": 80})
    post(
        client,
        consult.doctor,
        f"/encounters/{consult.enc_id}/notes",
        {"note_type": "PLAN", "content": "Rest"},
    )
    from app.core.db import set_tenant

    maker = client.app.state.sessionmaker  # type: ignore[attr-defined]
    attempts = [
        "update observations set value = 999",
        "delete from observations",
        "update clinical_notes set content = 'tampered'",
        "delete from clinical_notes",
        "update audit_logs set action = 'X'",
        "delete from audit_logs",
    ]
    for sql in attempts:
        with maker() as s:
            set_tenant(s, None, bypass=True)
            with pytest.raises(DBAPIError):
                s.execute(text(sql))
                s.commit()
    with maker() as s:  # bookkeeping columns remain updatable
        set_tenant(s, None, bypass=True)
        s.execute(text("update observations set is_current = false"))
        s.commit()


def test_events_and_audit_carry_no_clinical_content(
    client: TestClient, consult: Visit, superuser_engine: Engine
) -> None:
    enc = consult.enc_id
    post(client, consult.doctor, f"/encounters/{enc}/conditions", {"display": "Zzyzx syndrome"})
    post(
        client,
        consult.doctor,
        f"/encounters/{enc}/notes",
        {"note_type": "HPI", "content": "Secretword headache"},
    )
    post(client, consult.nurse, f"/encounters/{enc}/allergies", {"substance": "Quuxine"})
    audit = get(client, consult.admin, "/audit-logs", limit=200).text
    with superuser_engine.connect() as conn:
        events = str(conn.execute(text("select payload from clinical_events")).all())
    for blob in (audit, events):
        low = blob.lower()
        assert "zzyzx" not in low and "secretword" not in low and "quuxine" not in low


def test_timeline_shows_the_whole_journey_in_order(client: TestClient, consult: Visit) -> None:
    post(client, consult.nurse, f"/encounters/{consult.enc_id}/vitals", {"heart_rate": 80})
    post(
        client, consult.doctor, f"/encounters/{consult.enc_id}/complete"
    )  # blocked? no drafts -> completes
    kinds = [
        e["event_type"]
        for e in get(client, consult.doctor, f"/patients/{consult.patient['id']}/timeline").json()
    ]
    for expected in (
        "PATIENT_REGISTERED",
        "PATIENT_CHECKED_IN",
        "TRIAGE_STARTED",
        "VITAL_RECORDED",
        "ENCOUNTER_STARTED",
        "ENCOUNTER_COMPLETED",
    ):
        assert expected in kinds, expected
    assert (
        kinds.index("ENCOUNTER_COMPLETED")
        < kinds.index("TRIAGE_STARTED")
        < kinds.index("PATIENT_REGISTERED")
    )


def test_cross_tenant_facts_cannot_be_verified_or_edited(
    client: TestClient, visit: Visit, org_b: H
) -> None:
    a = post(
        client, visit.nurse, f"/encounters/{visit.enc_id}/allergies", {"substance": "Peanuts"}
    ).json()
    doc_b, _ = make_staff(client, org_b, "dr@beta.example.com", "doctor", "beta-hospital")
    nurse_b, _ = make_staff(client, org_b, "n2@beta.example.com", "nurse", "beta-hospital")
    assert (
        post(
            client, nurse_b, f"/clinical/allergies/{a['id']}/verify", {"action": "confirm"}
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"{API}/allergies/{a['id']}", headers=nurse_b, json={"severity": "MILD"}
        ).status_code
        == 404
    )


def test_nurses_cannot_verify_diagnoses(client: TestClient, consult: Visit) -> None:
    c = post(
        client,
        consult.doctor,
        f"/encounters/{consult.enc_id}/conditions",
        {"display": "Viral fever"},
    ).json()
    assert (
        post(
            client, consult.nurse, f"/clinical/conditions/{c['id']}/verify", {"action": "confirm"}
        ).status_code
        == 403
    )
    assert (
        post(
            client,
            consult.nurse,
            f"/clinical/conditions/{c['id']}/verify",
            {"action": "reject", "reason": "no"},
        ).status_code
        == 403
    )
    assert (
        post(
            client, consult.doctor, f"/clinical/conditions/{c['id']}/verify", {"action": "confirm"}
        ).status_code
        == 200
    )
