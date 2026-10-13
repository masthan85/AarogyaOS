from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import set_tenant
from tests.clinical_helpers import API, Visit, get, make_visit, post, rx_body
from tests.conftest import make_staff

H = dict[str, str]


@pytest.fixture
def v(client: TestClient, org_a: H) -> Visit:
    return make_visit(client, org_a, stage="consult")


@pytest.fixture
def lab(client: TestClient, org_a: H) -> H:
    return make_staff(
        client, org_a, "lab@alpha-clinic.example.com", "lab_technician", "alpha-clinic"
    )[0]


@pytest.fixture
def radiology(client: TestClient, org_a: H) -> H:
    return make_staff(
        client, org_a, "rad@alpha-clinic.example.com", "radiology_technician", "alpha-clinic"
    )[0]


def placed(
    client: TestClient, v: Visit, category: str = "LAB", name: str = "HbA1c"
) -> dict[str, Any]:
    o = post(
        client,
        v.doctor,
        f"/encounters/{v.enc_id}/orders",
        {"category": category, "name": name, "reason": "Diabetes review"},
    )
    assert o.status_code == 201, o.text
    p = post(client, v.doctor, f"/orders/{o.json()['id']}/place")
    assert p.status_code == 200, p.text
    return p.json()


def test_only_the_treating_doctor_orders(client: TestClient, v: Visit) -> None:
    url = f"/encounters/{v.enc_id}/orders"
    for h in (v.nurse, v.recep, v.admin):
        assert post(client, h, url, {"category": "LAB", "name": "CBC"}).status_code == 403
    assert post(client, v.doctor, url, {"category": "LAB", "name": "C"}).status_code == 422
    assert post(client, v.doctor, url, {"category": "PHARMACY", "name": "CBC"}).status_code == 422


def test_drafts_are_private_and_placing_makes_them_visible_to_the_right_department(
    client: TestClient, v: Visit, lab: H, radiology: H
) -> None:
    draft = post(
        client, v.doctor, f"/encounters/{v.enc_id}/orders", {"category": "LAB", "name": "CBC"}
    ).json()
    assert draft["status"] == "DRAFT" and draft["source"] == "DOCTOR_ENTERED"
    assert get(client, lab, "/orders").json() == []  # a draft is not an order yet
    assert (
        post(
            client, lab, f"/orders/{draft['id']}/results", {"test_name": "CBC", "value_text": "x"}
        ).status_code
        == 409
    )
    placed_order = post(client, v.doctor, f"/orders/{draft['id']}/place").json()
    assert placed_order["status"] == "ORDERED" and placed_order["ordered_at"]
    seen = get(client, lab, "/orders").json()
    assert [o["id"] for o in seen] == [draft["id"]] and seen[0]["patient_name"] == "Lakshmi Devi"
    assert get(client, radiology, "/orders").json() == []
    assert (
        post(
            client,
            radiology,
            f"/orders/{draft['id']}/results",
            {"test_name": "CBC", "value_text": "x"},
        ).status_code
        == 404
    )
    assert (
        post(client, v.doctor, f"/orders/{draft['id']}/place").status_code == 409
    )  # already placed


def test_lab_result_interpretation_is_deterministic_from_the_lab_reference_range(
    client: TestClient, v: Visit, lab: H
) -> None:
    o = placed(client, v)

    def result(value: str, **kw: Any) -> Any:
        return post(
            client,
            lab,
            f"/orders/{o['id']}/results",
            {
                "test_name": "HbA1c",
                "value_numeric": value,
                "unit": "%",
                "ref_low": "4.0",
                "ref_high": "5.6",
                "critical_high": "12",
                **kw,
            },
        )

    r = result("8.2")
    assert r.status_code == 201 and r.json()["interpretation"] == "HIGH"
    assert result("5.0").json()["interpretation"] == "NORMAL"
    assert result("3.1").json()["interpretation"] == "LOW"
    assert result("13").json()["interpretation"] == "CRITICAL_HIGH"
    no_range = post(
        client,
        lab,
        f"/orders/{o['id']}/results",
        {"test_name": "Culture", "value_text": "No growth"},
    )
    assert no_range.json()["interpretation"] == "UNKNOWN"
    assert post(client, lab, f"/orders/{o['id']}/results", {"test_name": "x"}).status_code == 422
    assert get(client, v.doctor, "/orders", encounter_id=v.enc_id).json()[0]["status"] == "RESULTED"


def test_abnormal_results_wait_for_review_and_raise_alerts(
    client: TestClient, v: Visit, lab: H
) -> None:
    o = placed(client, v)
    post(
        client,
        lab,
        f"/orders/{o['id']}/results",
        {"test_name": "HbA1c", "value_numeric": "8.2", "ref_high": "5.6", "unit": "%"},
    )
    pid = v.patient["id"]
    state = get(client, v.doctor, f"/patients/{pid}/clinical-state").json()
    assert any(a["code"] == "RESULT_REVIEW" and a["level"] == "WARNING" for a in state["alerts"])
    pending = get(client, v.doctor, "/results/awaiting-review").json()
    assert len(pending) == 1
    assert get(client, v.nurse, "/results/awaiting-review").status_code == 403
    assert post(client, v.nurse, f"/results/{pending[0]['id']}/review").status_code == 403
    reviewed = post(client, v.doctor, f"/results/{pending[0]['id']}/review")
    assert reviewed.status_code == 200 and reviewed.json()["reviewed_at"]
    assert get(client, v.doctor, "/results/awaiting-review").json() == []
    state = get(client, v.doctor, f"/patients/{pid}/clinical-state").json()
    assert not any(a["code"] == "RESULT_REVIEW" for a in state["alerts"])
    kinds = [e["event_type"] for e in get(client, v.doctor, f"/patients/{pid}/timeline").json()]
    assert {"INVESTIGATION_ORDERED", "RESULT_RECEIVED", "RESULT_REVIEWED"} <= set(kinds)


def test_review_queue_shows_critical_first_and_only_my_orders(
    client: TestClient, v: Visit, lab: H
) -> None:
    o = placed(client, v)
    for val in ("5.0", "13"):
        post(
            client,
            lab,
            f"/orders/{o['id']}/results",
            {"test_name": "HbA1c", "value_numeric": val, "ref_high": "5.6", "critical_high": "12"},
        )
    queue = get(client, v.doctor, "/results/awaiting-review").json()
    assert [r["interpretation"] for r in queue] == ["CRITICAL_HIGH", "NORMAL"]


def test_cancel_rules(client: TestClient, v: Visit, lab: H) -> None:
    o = placed(client, v)
    cancelled = post(client, v.doctor, f"/orders/{o['id']}/cancel", {"reason": "Not needed now"})
    assert cancelled.json()["status"] == "CANCELLED"
    assert (
        post(
            client, lab, f"/orders/{o['id']}/results", {"test_name": "x", "value_text": "y"}
        ).status_code
        == 409
    )
    o2 = placed(client, v, name="Lipid profile")
    post(client, lab, f"/orders/{o2['id']}/results", {"test_name": "LDL", "value_numeric": "100"})
    assert (
        post(client, v.doctor, f"/orders/{o2['id']}/cancel", {"reason": "Too late"}).status_code
        == 409
    )


def test_reported_results_cannot_be_altered_in_the_database(
    client: TestClient, v: Visit, lab: H
) -> None:
    o = placed(client, v)
    post(
        client,
        lab,
        f"/orders/{o['id']}/results",
        {"test_name": "HbA1c", "value_numeric": "8.2", "ref_high": "5.6"},
    )
    maker = client.app.state.sessionmaker  # type: ignore[attr-defined]
    for sql in (
        "update investigation_results set value_numeric = 5",
        "delete from investigation_results",
    ):
        with maker() as s:
            set_tenant(s, None, bypass=True)
            with pytest.raises(DBAPIError):
                s.execute(text(sql))
                s.commit()


def test_orders_are_tenant_isolated(client: TestClient, v: Visit, org_b: H) -> None:
    o = placed(client, v)
    lab_b, _ = make_staff(client, org_b, "lab@beta.example.com", "lab_technician", "beta-hospital")
    doc_b, _ = make_staff(client, org_b, "dr@beta.example.com", "doctor", "beta-hospital")
    assert get(client, lab_b, "/orders").json() == []
    assert (
        post(
            client, lab_b, f"/orders/{o['id']}/results", {"test_name": "x", "value_text": "y"}
        ).status_code
        == 404
    )
    assert (
        post(client, doc_b, f"/orders/{o['id']}/cancel", {"reason": "no no no"}).status_code == 404
    )


def test_followups(client: TestClient, v: Visit) -> None:
    url = f"/encounters/{v.enc_id}/follow-ups"
    due = (date.today() + timedelta(days=7)).isoformat()
    assert post(client, v.nurse, url, {"due_date": due, "reason": "Review"}).status_code == 403
    assert (
        post(client, v.doctor, url, {"due_date": "2000-01-01", "reason": "Review"}).status_code
        == 422
    )
    fu = post(client, v.doctor, url, {"due_date": due, "reason": "Review BP", "kind": "REVIEW"})
    assert fu.status_code == 201 and fu.json()["status"] == "PENDING"
    assert [
        f["id"] for f in get(client, v.recep, "/follow-ups", patient_id=v.patient["id"]).json()
    ] == [fu.json()["id"]]
    assert (
        get(client, v.recep, "/follow-ups", due_on_or_before=date.today().isoformat()).json() == []
    )
    assert (
        post(
            client, v.recep, f"/follow-ups/{fu.json()['id']}/status", {"status": "COMPLETED"}
        ).status_code
        == 403
    )
    done = post(client, v.doctor, f"/follow-ups/{fu.json()['id']}/status", {"status": "COMPLETED"})
    assert done.json()["status"] == "COMPLETED"
    assert (
        post(
            client, v.doctor, f"/follow-ups/{fu.json()['id']}/status", {"status": "CANCELLED"}
        ).status_code
        == 409
    )
    assert get(client, v.admin, "/follow-ups").status_code == 403


def test_full_clinical_journey_end_to_end(client: TestClient, org_a: H) -> None:
    """Reception to follow-up, with the AI-free workflow doing everything a clinic needs."""
    v = make_visit(client, org_a)  # patient registered, walked in, nurse opened triage
    enc, pid = v.enc_id, v.patient["id"]
    # Nurse: complaint, vitals, allergy history, triage category
    assert (
        post(
            client,
            v.nurse,
            f"/encounters/{enc}/notes",
            {
                "note_type": "CHIEF_COMPLAINT",
                "content": "Fever and cough for 2 days",
                "source": "PATIENT_REPORTED",
            },
        ).status_code
        == 201
    )
    assert (
        post(
            client,
            v.nurse,
            f"/encounters/{enc}/vitals",
            {
                "temperature": {"value": 102, "unit": "F"},
                "spo2": 96,
                "heart_rate": 96,
                "systolic_bp": 128,
                "diastolic_bp": 82,
            },
        ).status_code
        == 201
    )
    assert (
        post(client, v.nurse, f"/encounters/{enc}/allergies", {"is_nka": True}).status_code == 201
    )
    assert (
        client.put(
            f"{API}/encounters/{enc}/triage-category", headers=v.nurse, json={"category": "URGENT"}
        ).json()["triage_category"]
        == "URGENT"
    )
    # Doctor sees the prepared picture, then takes over
    state = get(client, v.doctor, f"/patients/{pid}/clinical-state").json()
    assert any(a["code"] == "ABNORMAL_VITAL" for a in state["alerts"])
    assert (
        post(
            client, v.doctor, "/encounters/consultation", {"appointment_id": v.appt_id}
        ).status_code
        == 200
    )
    # Consultation: history, exam, diagnosis, investigation, prescription, follow-up
    assert (
        post(
            client,
            v.doctor,
            f"/encounters/{enc}/notes",
            {"note_type": "EXAMINATION", "content": "Throat congested; chest clear"},
        ).status_code
        == 201
    )
    assert (
        post(
            client,
            v.doctor,
            f"/encounters/{enc}/conditions",
            {"display": "Acute viral fever", "certainty": "PROVISIONAL"},
        ).status_code
        == 201
    )
    order = post(
        client,
        v.doctor,
        f"/encounters/{enc}/orders",
        {"category": "LAB", "name": "Complete blood count", "priority": "URGENT"},
    ).json()
    assert post(client, v.doctor, f"/orders/{order['id']}/place").status_code == 200
    rx = post(
        client, v.doctor, f"/encounters/{enc}/prescriptions", rx_body("Paracetamol 650 mg")
    ).json()
    assert post(client, v.doctor, f"/prescriptions/{rx['id']}/sign").status_code == 200
    due = (date.today() + timedelta(days=5)).isoformat()
    assert (
        post(
            client,
            v.doctor,
            f"/encounters/{enc}/follow-ups",
            {"due_date": due, "reason": "Review with CBC result"},
        ).status_code
        == 201
    )
    assert post(client, v.doctor, f"/encounters/{enc}/complete").status_code == 200
    # Everything is on one timeline, and the visit is closed.
    detail = get(client, v.doctor, f"/encounters/{enc}").json()
    assert detail["encounter"]["status"] == "COMPLETED"
    assert (
        len(detail["notes"]) == 2
        and len(detail["vitals"]) == 5
        and len(detail["prescriptions"]) == 1
    )
    kinds = {e["event_type"] for e in get(client, v.doctor, f"/patients/{pid}/timeline").json()}
    assert {
        "TRIAGE_STARTED",
        "VITAL_RECORDED",
        "ENCOUNTER_STARTED",
        "INVESTIGATION_ORDERED",
        "PRESCRIPTION_SIGNED",
        "FOLLOWUP_CREATED",
        "ENCOUNTER_COMPLETED",
    } <= kinds
    # Nothing in the audit trail was lost along the way
    assert get(client, v.admin, "/audit-logs", action="PRESCRIPTION_SIGNED").json()


def test_draft_orders_are_hidden_from_nurses_everywhere(client: TestClient, v: Visit) -> None:
    draft = post(
        client, v.doctor, f"/encounters/{v.enc_id}/orders", {"category": "LAB", "name": "CBC"}
    ).json()
    assert get(client, v.nurse, "/orders", encounter_id=v.enc_id).json() == []
    assert get(client, v.nurse, f"/encounters/{v.enc_id}").json()["orders"] == []
    assert [o["id"] for o in get(client, v.doctor, f"/encounters/{v.enc_id}").json()["orders"]] == [
        draft["id"]
    ]
    post(client, v.doctor, f"/orders/{draft['id']}/place")
    assert len(get(client, v.nurse, "/orders", encounter_id=v.enc_id).json()) == 1
