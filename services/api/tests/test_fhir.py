"""FHIR R4 export: structure, exclusions, provenance and access control."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fhir.resources.R4B.bundle import Bundle
from fhir.resources.R4B.capabilitystatement import CapabilityStatement
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.interop import fhir
from tests.clinical_helpers import API, Visit, make_visit, post, rx_body
from tests.helpers import make_facility, make_practitioner

H = dict[str, str]


@pytest.fixture
def done(client: TestClient, org_a: H) -> Visit:
    v = make_visit(client, org_a, stage="consult")
    e = v.enc_id
    assert (
        post(
            client, v.nurse, f"/encounters/{e}/vitals", {"heart_rate": 118, "spo2": 97}
        ).status_code
        == 201
    )
    assert (
        post(
            client,
            v.nurse,
            f"/encounters/{e}/allergies",
            {"substance": "Penicillin", "certainty": "POSSIBLE", "source": "PATIENT_REPORTED"},
        ).status_code
        == 201
    )
    assert (
        post(
            client,
            v.doctor,
            f"/encounters/{e}/notes",
            {"note_type": "HPI", "content": "Fever for three days <urgent> & cough"},
        ).status_code
        == 201
    )
    assert (
        post(
            client,
            v.doctor,
            f"/encounters/{e}/conditions",
            {"display": "Viral fever", "certainty": "SUSPECTED", "category": "DIAGNOSIS"},
        ).status_code
        == 201
    )
    rx = post(
        client, v.doctor, f"/encounters/{e}/prescriptions", rx_body("Paracetamol 500 mg")
    ).json()
    order = post(
        client, v.doctor, f"/encounters/{e}/orders", {"category": "LAB", "name": "CBC"}
    ).json()
    warns = post(client, v.doctor, f"/prescriptions/{rx['id']}/safety-check").json()["warnings"]
    signed = post(
        client,
        v.doctor,
        f"/prescriptions/{rx['id']}/sign",
        {"acknowledged_warning_codes": [w["code"] for w in warns]},
    )
    assert signed.status_code == 200, signed.text
    assert post(client, v.doctor, f"/orders/{order['id']}/place").status_code == 200
    assert post(client, v.doctor, f"/encounters/{e}/complete").status_code == 200, "complete"
    return v


def export(client: TestClient, v: Visit, h: H | None = None) -> Any:
    return client.get(f"{API}/fhir/Encounter/{v.enc_id}/$export-document", headers=h or v.doctor)


def test_a_completed_visit_exports_as_a_valid_fhir_document(
    client: TestClient, done: Visit
) -> None:
    r = export(client, done)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/fhir+json")
    body = r.json()
    bundle = Bundle.model_validate(body)  # structural validation against the R4B models
    assert (
        bundle.type == "document" and body["entry"][0]["resource"]["resourceType"] == "Composition"
    )
    kinds = [e["resource"]["resourceType"] for e in body["entry"]]
    assert {
        "Patient",
        "Practitioner",
        "Organization",
        "Encounter",
        "Observation",
        "Condition",
        "AllergyIntolerance",
        "MedicationRequest",
        "ServiceRequest",
    } <= set(kinds)
    from fhir.resources.R4B import get_fhir_model_class

    for e in body["entry"]:
        get_fhir_model_class(e["resource"]["resourceType"]).model_validate(e["resource"])


def test_every_reference_in_the_document_resolves_inside_it(
    client: TestClient, done: Visit
) -> None:
    body = export(client, done).json()
    have = {f"{e['resource']['resourceType']}/{e['resource']['id']}" for e in body["entry"]}

    def refs(node: Any) -> list[str]:
        if isinstance(node, dict):
            found = [node["reference"]] if isinstance(node.get("reference"), str) else []
            return found + [x for v in node.values() for x in refs(v)]
        if isinstance(node, list):
            return [x for v in node for x in refs(v)]
        return []

    missing = [x for x in refs(body["entry"]) if x not in have]
    assert not missing, missing


def test_provenance_and_uncertainty_travel_with_the_data(client: TestClient, done: Visit) -> None:
    entries = [e["resource"] for e in export(client, done).json()["entry"]]
    cond = next(r for r in entries if r["resourceType"] == "Condition")
    assert cond["verificationStatus"]["coding"][0]["code"] == "unconfirmed"  # SUSPECTED
    allergy = next(r for r in entries if r["resourceType"] == "AllergyIntolerance")
    assert allergy["verificationStatus"]["coding"][0]["code"] == "unconfirmed"  # POSSIBLE
    tags = {t["code"] for t in allergy["meta"]["tag"]}
    assert "PATIENT_REPORTED" in tags and "UNVERIFIED" in tags
    hr = next(
        r
        for r in entries
        if r["resourceType"] == "Observation" and r["code"].get("text") == "Heart rate"
    )
    assert hr["code"]["coding"][0] == {
        "system": "http://loinc.org",
        "code": "8867-4",
        "display": "Heart rate",
    }
    assert hr["interpretation"][0]["coding"][0]["code"] == "H"


def test_only_signed_and_placed_items_leave_and_minimum_data_is_shared(
    client: TestClient, done: Visit
) -> None:
    entries = [e["resource"] for e in export(client, done).json()["entry"]]
    assert all(r["status"] == "active" for r in entries if r["resourceType"] == "MedicationRequest")
    assert all(
        r["status"] in ("active", "completed")
        for r in entries
        if r["resourceType"] == "ServiceRequest"
    )
    patient = next(r for r in entries if r["resourceType"] == "Patient")
    assert "address" not in patient and not any(
        "abha" in str(i).lower() for i in patient["identifier"]
    )


def test_narrative_is_escaped(client: TestClient, done: Visit) -> None:
    comp = export(client, done).json()["entry"][0]["resource"]
    html = " ".join(s["text"]["div"] for s in comp["section"] if "text" in s)
    assert "&lt;urgent&gt;" in html and "<urgent>" not in html and "&amp;" in html


def test_a_corrected_vital_exports_only_its_current_version(client: TestClient, org_a: H) -> None:
    v = make_visit(client, org_a, stage="consult")
    created = post(client, v.nurse, f"/encounters/{v.enc_id}/vitals", {"heart_rate": 118}).json()
    first = created[0] if isinstance(created, list) else created["observations"][0]
    fixed = client.put(f"{API}/observations/{first['id']}", headers=v.nurse, json={"value": 80})
    assert fixed.status_code == 200, fixed.text
    assert export(client, v).status_code == 409  # a visit still open is not exported
    assert post(client, v.doctor, f"/encounters/{v.enc_id}/complete").status_code == 200
    entries = [e["resource"] for e in export(client, v).json()["entry"]]
    rates = [r for r in entries if r.get("code", {}).get("text") == "Heart rate"]
    assert [r["valueQuantity"]["value"] for r in rates] == [80]
    assert all("profile" not in r.get("meta", {}) for r in entries)


def test_open_visits_and_other_doctors_and_other_roles_are_refused_with_operation_outcomes(
    client: TestClient, done: Visit, org_a: H, org_b: H
) -> None:
    for h in (done.nurse, done.recep):
        assert export(client, done, h).status_code == 403
    other, _ = make_practitioner(
        client, org_a, "alpha-clinic", done.facility, "dr.other@x.example.com"
    )
    r = export(client, done, other)
    assert r.status_code == 403 and r.json()["resourceType"] == "OperationOutcome"
    doctor_b, _ = make_practitioner(client, org_b, "beta-hospital", make_facility(client, org_b))
    r = export(client, done, doctor_b)
    assert r.status_code == 404 and r.json()["issue"][0]["code"] == "not-found"


def test_patient_read_and_capability_statement(client: TestClient, done: Visit) -> None:
    r = client.get(f"{API}/fhir/Patient/{done.patient['id']}", headers=done.doctor)
    assert r.status_code == 200 and r.json()["resourceType"] == "Patient"
    meta = client.get(f"{API}/fhir/metadata", headers=done.doctor).json()
    CapabilityStatement.model_validate(meta)
    assert (
        meta["fhirVersion"] == "4.0.1"
        and "no ABDM profile conformance" in meta["implementation"]["description"]
    )
    assert "profile" not in meta and "supportedProfile" not in str(meta)


def test_exports_are_audited_without_clinical_content(
    client: TestClient, done: Visit, db: Session
) -> None:
    export(client, done)
    rows = db.execute(text("select action, after from audit_logs where action like 'FHIR_%'")).all()
    assert [r[0] for r in rows] == ["FHIR_DOCUMENT_EXPORTED"]
    assert "Penicillin" not in str(rows)


# ---- mapper unit tests (no database) --------------------------------------------------------


def _fact(**kw: Any) -> SimpleNamespace:
    base: dict[str, Any] = dict(  # noqa: C408
        id="11111111-1111-1111-1111-111111111111",
        patient_id="22222222-2222-2222-2222-222222222222",
        encounter_id=None,
        source="AI_EXTRACTED",
        verification_state="CLINICIAN_EDITED",
        recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return SimpleNamespace(**{**base, **kw})


def test_ai_sourced_facts_are_tagged_as_such() -> None:
    c = _fact(
        certainty="CONFIRMED",
        clinical_status="ACTIVE",
        category="DIAGNOSIS",
        display="x",
        code=None,
        code_system=None,
        note=None,
    )
    tags = {t["code"] for t in fhir.condition(c)["meta"]["tag"]}
    assert tags == {"AI_EXTRACTED", "CLINICIAN_EDITED"}


def test_an_estimated_birth_date_is_marked_and_unknown_gender_is_not_guessed() -> None:
    p = SimpleNamespace(
        id="33333333-3333-3333-3333-333333333333",
        organisation_id="44444444-4444-4444-4444-444444444444",
        mrn="M1",
        full_name="A B",
        date_of_birth=date(1980, 1, 1),
        dob_is_estimated=True,
        administrative_gender="unknown",
        mobile=None,
        preferred_language="hi-IN",
        status="ACTIVE",
    )
    out = fhir.patient(p)
    assert out["gender"] == "unknown" and out["_birthDate"]["extension"][0]["valueBoolean"] is True


def test_uncoded_vitals_stay_text_and_no_known_allergies_is_not_an_allergy_resource() -> None:
    o = _fact(
        code="BLOOD_GLUCOSE",
        value=Decimal("110.00"),
        unit="mg/dL",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        interpretation="NORMAL",
        context="FASTING",
    )
    out = fhir.vital(o)
    assert "coding" not in out["code"] and out["valueQuantity"] == {"value": 110, "unit": "mg/dL"}
    assert fhir.allergy(_fact(is_nka=True)) == {}
