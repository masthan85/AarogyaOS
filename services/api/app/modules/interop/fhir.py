"""Mapping of the clinical record to plain FHIR R4 resources (dicts, no database access).

What this is NOT: it does not claim conformance to the ABDM / NRCeS profiles. Those profile pages
could not be read from the build environment, so no `meta.profile` is asserted and no ABDM-specific
rules are implemented. These are base-R4 resources that a later profile layer can specialise.

Rules that apply to every mapper:
* Only what a clinician has settled leaves the system: rejected facts and superseded versions are
  excluded, drafts (prescriptions, orders) are excluded, AI candidates are never exported.
* Provenance travels with the data as `meta.tag`s (source and verification state), because a
  receiver must be able to tell patient-reported from clinician-confirmed.
* Codes are only emitted where the standard fixes them (FHIR core code systems, the LOINC vital-sign
  codes from the FHIR vital-signs profile). Everything else is free text; nothing is guessed.
* Identifiers use an `example.com` placeholder namespace until the organisation's registered
  identifier systems are configured.
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

FHIR_VERSION = "4.0.1"
JSON_TYPE = "application/fhir+json"
NS = "https://aarogyaos.example/fhir"
TAG_SOURCE = f"{NS}/CodeSystem/source"
TAG_VERIFICATION = f"{NS}/CodeSystem/verification"

LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"
OBS_CATEGORY = "http://terminology.hl7.org/CodeSystem/observation-category"
INTERPRETATION = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"
CONDITION_CLINICAL = "http://terminology.hl7.org/CodeSystem/condition-clinical"
CONDITION_VERIFICATION = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
ALLERGY_CLINICAL = "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical"
ALLERGY_VERIFICATION = "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification"
ACT_CODE = "http://terminology.hl7.org/CodeSystem/v3-ActCode"

# LOINC codes and UCUM units fixed by the FHIR core vital-signs profile. Glucose and pain score have
# no code here on purpose: they stay free text rather than risk a wrong code.
VITAL_CODES: dict[str, tuple[str, str, str, str]] = {
    # code: (loinc, loinc display, ucum code, unit text)
    "TEMPERATURE_C": ("8310-5", "Body temperature", "Cel", "°C"),
    "HEART_RATE": ("8867-4", "Heart rate", "/min", "beats/minute"),
    "RESPIRATORY_RATE": ("9279-1", "Respiratory rate", "/min", "breaths/minute"),
    "SPO2": ("59408-5", "Oxygen saturation in Arterial blood by Pulse oximetry", "%", "%"),
    "SYSTOLIC_BP": ("8480-6", "Systolic blood pressure", "mm[Hg]", "mmHg"),
    "DIASTOLIC_BP": ("8462-4", "Diastolic blood pressure", "mm[Hg]", "mmHg"),
    "HEIGHT_CM": ("8302-2", "Body height", "cm", "cm"),
    "WEIGHT_KG": ("29463-7", "Body weight", "kg", "kg"),
}
VITAL_TEXT = {"BLOOD_GLUCOSE": "Blood glucose", "PAIN_SCORE": "Pain score"}
INTERPRETATION_CODES = {
    "NORMAL": ("N", "Normal"),
    "HIGH": ("H", "High"),
    "LOW": ("L", "Low"),
    "CRITICAL_HIGH": ("HH", "Critical high"),
    "CRITICAL_LOW": ("LL", "Critical low"),
}
EXCLUDED_VERIFICATION = {"CLINICIAN_REJECTED"}


def ref(resource_type: str, rid: uuid.UUID | str) -> dict[str, str]:
    return {"reference": f"{resource_type}/{rid}"}


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z") if dt else None


def _meta(obj: Any) -> dict[str, Any]:
    tags = []
    if getattr(obj, "source", None):
        tags.append({"system": TAG_SOURCE, "code": obj.source})
    if getattr(obj, "verification_state", None):
        tags.append({"system": TAG_VERIFICATION, "code": obj.verification_state})
    meta: dict[str, Any] = {}
    if tags:
        meta["tag"] = tags
    return meta


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    """Drop empty values: FHIR forbids empty strings, empty arrays and empty objects."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if v is None or v == "" or v == [] or v == {}:
            continue
        out[k] = v
    return out


def exportable(fact: Any) -> bool:
    return bool(fact.is_current) and fact.verification_state not in EXCLUDED_VERIFICATION


def _num(value: Decimal | float | int) -> float | int:
    f = float(value)
    return int(f) if f.is_integer() else f


# ---- administrative -------------------------------------------------------------------------


def patient(p: Any) -> dict[str, Any]:
    """Minimum necessary: name, gender, birth date (flagged when estimated), MRN, phone, language.
    The address and the encrypted ABHA identifier are not included."""
    birth: dict[str, Any] = {}
    if p.date_of_birth:
        birth["birthDate"] = p.date_of_birth.isoformat()
        if p.dob_is_estimated:
            birth["_birthDate"] = {
                "extension": [{"url": f"{NS}/StructureDefinition/estimated", "valueBoolean": True}]
            }
    return _clean(
        {
            "resourceType": "Patient",
            "id": str(p.id),
            "identifier": [
                {
                    "use": "usual",
                    "type": {"text": "Medical record number"},
                    "system": f"{NS}/identifier/mrn/{p.organisation_id}",
                    "value": p.mrn,
                }
            ],
            "active": p.status == "ACTIVE",
            "name": [{"text": p.full_name}],
            "telecom": [{"system": "phone", "value": p.mobile}] if p.mobile else [],
            "gender": p.administrative_gender
            if p.administrative_gender in ("male", "female", "other")
            else "unknown",
            **birth,
            "communication": [
                {
                    "language": {
                        "coding": [{"system": "urn:ietf:bcp:47", "code": p.preferred_language}]
                    },
                    "preferred": True,
                }
            ]
            if p.preferred_language
            else [],
        }
    )


def practitioner(pr: Any, full_name: str) -> dict[str, Any]:
    ident = (
        [
            {
                "type": {"text": "Medical registration number (not verified)"},
                "system": f"{NS}/identifier/medical-registration",
                "value": pr.registration_number,
            }
        ]
        if pr.registration_number
        else []
    )
    return _clean(
        {
            "resourceType": "Practitioner",
            "id": str(pr.id),
            "identifier": ident,
            "active": pr.status == "ACTIVE",
            "name": [{"text": full_name}],
            "qualification": [{"code": {"text": pr.specialty}}] if pr.specialty else [],
        }
    )


def organisation(f: Any) -> dict[str, Any]:
    return _clean(
        {
            "resourceType": "Organization",
            "id": str(f.id),
            "identifier": [{"system": f"{NS}/identifier/facility", "value": f.code}],
            "active": f.status == "ACTIVE",
            "name": f.name,
            "address": [{"text": f.address}] if f.address else [],
        }
    )


def encounter(e: Any) -> dict[str, Any]:
    status = {"TRIAGE": "in-progress", "IN_PROGRESS": "in-progress", "COMPLETED": "finished"}.get(
        e.status, "unknown"
    )
    period = _clean({"start": _iso(e.started_at), "end": _iso(e.ended_at)})
    return _clean(
        {
            "resourceType": "Encounter",
            "id": str(e.id),
            "status": status,
            "class": {"system": ACT_CODE, "code": "AMB", "display": "ambulatory"},
            "subject": ref("Patient", e.patient_id),
            "participant": [{"individual": ref("Practitioner", e.practitioner_id)}]
            if e.practitioner_id
            else [],
            "period": period,
            "serviceProvider": ref("Organization", e.facility_id),
        }
    )


# ---- clinical facts -------------------------------------------------------------------------


def vital(o: Any) -> dict[str, Any]:
    spec = VITAL_CODES.get(o.code)
    if spec:
        loinc, display, ucum, unit = spec
        code = {"coding": [{"system": LOINC, "code": loinc, "display": display}], "text": display}
        quantity = {"value": _num(o.value), "unit": unit, "system": UCUM, "code": ucum}
    else:
        code = {"text": VITAL_TEXT.get(o.code, o.code.replace("_", " ").title())}
        quantity = {"value": _num(o.value), "unit": o.unit}
    interp = INTERPRETATION_CODES.get(o.interpretation)
    return _clean(
        {
            "resourceType": "Observation",
            "id": str(o.id),
            "meta": _meta(o),
            "status": "final" if o.verification_state != "UNVERIFIED" else "preliminary",
            "category": [{"coding": [{"system": OBS_CATEGORY, "code": "vital-signs"}]}],
            "code": code,
            "subject": ref("Patient", o.patient_id),
            "encounter": ref("Encounter", o.encounter_id) if o.encounter_id else None,
            "effectiveDateTime": _iso(o.observed_at),
            "valueQuantity": quantity,
            "interpretation": [
                {"coding": [{"system": INTERPRETATION, "code": interp[0], "display": interp[1]}]}
            ]
            if interp
            else [],
            "note": [{"text": f"Context: {o.context}"}] if o.context else [],
        }
    )


def condition(c: Any) -> dict[str, Any]:
    verification = {
        "CONFIRMED": "confirmed",
        "PROVISIONAL": "provisional",
        "SUSPECTED": "unconfirmed",
    }.get(c.certainty, "unconfirmed")
    clinical = {"ACTIVE": "active", "RESOLVED": "resolved", "INACTIVE": "inactive"}.get(
        c.clinical_status, "active"
    )
    coding = (
        [{"system": c.code_system, "code": c.code, "display": c.display}]
        if c.code and c.code_system
        else []
    )
    return _clean(
        {
            "resourceType": "Condition",
            "id": str(c.id),
            "meta": _meta(c),
            "clinicalStatus": {"coding": [{"system": CONDITION_CLINICAL, "code": clinical}]},
            "verificationStatus": {
                "coding": [{"system": CONDITION_VERIFICATION, "code": verification}]
            },
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                            "code": "encounter-diagnosis"
                            if c.category == "DIAGNOSIS"
                            else "problem-list-item",
                        }
                    ]
                }
            ],
            "code": _clean({"coding": coding, "text": c.display}),
            "subject": ref("Patient", c.patient_id),
            "encounter": ref("Encounter", c.encounter_id) if c.encounter_id else None,
            "recordedDate": _iso(c.recorded_at),
            "note": [{"text": c.note}] if c.note else [],
        }
    )


def allergy(a: Any) -> dict[str, Any]:
    if a.is_nka:
        return {}  # "no known allergies" is a statement about absence; see composition note
    verification = {
        "CONFIRMED": "confirmed",
        "POSSIBLE": "unconfirmed",
        "HISTORICAL": "confirmed",
    }.get(a.certainty, "unconfirmed")
    clinical = (
        "inactive" if a.certainty == "HISTORICAL" or a.clinical_status != "ACTIVE" else "active"
    )
    criticality = {"SEVERE": "high", "MILD": "low"}.get(a.severity)
    category = {"MEDICATION": "medication", "FOOD": "food", "ENVIRONMENT": "environment"}.get(
        a.category
    )
    reaction = [{"manifestation": [{"text": a.reaction}]}] if a.reaction else []
    if reaction and a.severity in ("MILD", "MODERATE", "SEVERE"):
        reaction[0]["severity"] = a.severity.lower()
    return _clean(
        {
            "resourceType": "AllergyIntolerance",
            "id": str(a.id),
            "meta": _meta(a),
            "clinicalStatus": {"coding": [{"system": ALLERGY_CLINICAL, "code": clinical}]},
            "verificationStatus": {
                "coding": [{"system": ALLERGY_VERIFICATION, "code": verification}]
            },
            "category": [category] if category else [],
            "criticality": criticality,
            "code": {"text": a.substance},
            "patient": ref("Patient", a.patient_id),
            "encounter": ref("Encounter", a.encounter_id) if a.encounter_id else None,
            "recordedDate": _iso(a.recorded_at),
            "reaction": reaction,
        }
    )


def medication_statement(m: Any) -> dict[str, Any]:
    dosage = ", ".join(x for x in (m.dose, m.route, m.frequency) if x)
    return _clean(
        {
            "resourceType": "MedicationStatement",
            "id": str(m.id),
            "meta": _meta(m),
            "status": "active" if m.status == "ACTIVE" else "stopped",
            "medicationCodeableConcept": {"text": m.name},
            "subject": ref("Patient", m.patient_id),
            "context": ref("Encounter", m.encounter_id) if m.encounter_id else None,
            "dateAsserted": _iso(m.recorded_at),
            "informationSource": None,
            "dosage": [{"text": dosage}] if dosage else [],
        }
    )


def medication_request(rx: Any, item: Any, author: dict[str, str] | None) -> dict[str, Any]:
    text = ", ".join(
        x
        for x in (
            item.dose,
            item.route,
            item.frequency,
            f"for {item.duration_days} days" if item.duration_days else "",
        )
        if x
    )
    dosage = _clean({"text": text, "patientInstruction": item.instructions})
    coding = (
        [{"system": item.code_system, "code": item.medication_code, "display": item.medicine_name}]
        if item.medication_code and item.code_system
        else []
    )
    return _clean(
        {
            "resourceType": "MedicationRequest",
            "id": str(item.id),
            "status": "active" if rx.status == "SIGNED" else "cancelled",
            "intent": "order",
            "medicationCodeableConcept": _clean({"coding": coding, "text": item.medicine_name}),
            "subject": ref("Patient", rx.patient_id),
            "encounter": ref("Encounter", rx.encounter_id),
            "authoredOn": _iso(rx.signed_at),
            "requester": author,
            "dosageInstruction": [dosage],
            "dispenseRequest": {"quantity": {"value": item.quantity}} if item.quantity else {},
        }
    )


def service_request(s: Any) -> dict[str, Any]:
    status = {"ORDERED": "active", "RESULTED": "completed", "CANCELLED": "revoked"}.get(s.status)
    category = {"LAB": "Laboratory", "RADIOLOGY": "Imaging"}.get(s.category)
    return _clean(
        {
            "resourceType": "ServiceRequest",
            "id": str(s.id),
            "meta": _meta(s),
            "status": status or "unknown",
            "intent": "order",
            "category": [{"text": category}] if category else [],
            "priority": {"ROUTINE": "routine", "URGENT": "urgent", "STAT": "stat"}.get(s.priority),
            "code": {"text": s.name},
            "subject": ref("Patient", s.patient_id),
            "encounter": ref("Encounter", s.encounter_id),
            "authoredOn": _iso(s.ordered_at),
            "reasonCode": [{"text": s.reason}] if s.reason else [],
        }
    )


def lab_result(r: Any, encounter_id: uuid.UUID | None, patient_id: uuid.UUID) -> dict[str, Any]:
    value: dict[str, Any] = {}
    if r.value_numeric is not None:
        value["valueQuantity"] = _clean({"value": _num(r.value_numeric), "unit": r.unit})
    elif r.value_text:
        value["valueString"] = r.value_text
    rng = _clean(
        {
            "low": {"value": _num(r.ref_low), "unit": r.unit} if r.ref_low is not None else None,
            "high": {"value": _num(r.ref_high), "unit": r.unit} if r.ref_high is not None else None,
        }
    )
    interp = INTERPRETATION_CODES.get(r.interpretation)
    return _clean(
        {
            "resourceType": "Observation",
            "id": str(r.id),
            "meta": _meta(r),
            "status": "final",
            "category": [{"coding": [{"system": OBS_CATEGORY, "code": "laboratory"}]}],
            "code": {"text": r.test_name},
            "subject": ref("Patient", patient_id),
            "encounter": ref("Encounter", encounter_id) if encounter_id else None,
            "effectiveDateTime": _iso(r.reported_at),
            "basedOn": [ref("ServiceRequest", r.service_request_id)],
            **value,
            "interpretation": [
                {"coding": [{"system": INTERPRETATION, "code": interp[0], "display": interp[1]}]}
            ]
            if interp
            else [],
            "note": [{"text": r.comment}] if r.comment else [],
            "referenceRange": [rng] if rng else [],
        }
    )


# ---- document -------------------------------------------------------------------------------

NOTE_TITLES = {
    "CHIEF_COMPLAINT": "Reason for visit",
    "HPI": "History of present illness",
    "PAST_HISTORY": "Past history",
    "FAMILY_HISTORY": "Family history",
    "SOCIAL_HISTORY": "Social history",
    "EXAMINATION": "Examination",
    "ASSESSMENT": "Assessment",
    "PLAN": "Plan",
    "TRIAGE": "Triage",
    "GENERAL": "Other notes",
}


def _div(text: str) -> dict[str, str]:
    esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return {"status": "generated", "div": f'<div xmlns="http://www.w3.org/1999/xhtml">{esc}</div>'}


def composition(
    enc: Any,
    *,
    patient_ref: dict[str, str],
    author: dict[str, str],
    custodian: dict[str, str],
    notes: Iterable[Any],
    sections_refs: dict[str, list[dict[str, str]]],
    no_known_allergies: bool,
) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    by_type: dict[str, list[str]] = {}
    for n in notes:
        by_type.setdefault(n.note_type, []).append(n.content)
    for note_type, contents in by_type.items():
        sections.append(
            {
                "title": NOTE_TITLES.get(note_type, note_type.replace("_", " ").title()),
                "text": _div("\n".join(contents)),
            }
        )
    titles = {
        "Observation": "Vital signs and results",
        "Condition": "Diagnoses and problems",
        "AllergyIntolerance": "Allergies",
        "MedicationRequest": "Medicines prescribed",
        "MedicationStatement": "Medicines the patient takes",
        "ServiceRequest": "Tests ordered",
    }
    for rtype, title in titles.items():
        entries = sections_refs.get(rtype, [])
        if entries or (rtype == "AllergyIntolerance" and no_known_allergies):
            section: dict[str, Any] = {"title": title, "entry": entries}
            if not entries:
                section["text"] = _div("No known allergies recorded.")
                section["emptyReason"] = {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/list-empty-reason",
                            "code": "nilknown",
                        }
                    ]
                }
            sections.append(_clean(section))
    return _clean(
        {
            "resourceType": "Composition",
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"composition:{enc.id}")),
            "status": "final",
            "type": {
                "coding": [{"system": LOINC, "code": "11488-4", "display": "Consult note"}],
                "text": "Outpatient consultation",
            },
            "subject": patient_ref,
            "encounter": ref("Encounter", enc.id),
            "date": _iso(enc.ended_at or enc.started_at),
            "author": [author],
            "title": "Outpatient consultation",
            "custodian": custodian,
            "section": sections,
        }
    )


def document_bundle(comp: dict[str, Any], resources: list[dict[str, Any]]) -> dict[str, Any]:
    """A FHIR document: the Composition first, then everything it refers to."""
    entries = [{"fullUrl": f"urn:uuid:{comp['id']}", "resource": comp}]
    entries += [
        {"fullUrl": f"{r['resourceType']}/{r['id']}", "resource": r} for r in resources if r
    ]
    return {
        "resourceType": "Bundle",
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"bundle:{comp['id']}")),
        "type": "document",
        "timestamp": _iso(datetime.now(UTC)),
        "identifier": {"system": f"{NS}/identifier/document", "value": comp["id"]},
        "entry": entries,
    }


def capability_statement(base_url: str) -> dict[str, Any]:
    return {
        "resourceType": "CapabilityStatement",
        "status": "draft",
        "date": _iso(datetime.now(UTC)),
        "kind": "instance",
        "software": {"name": "AarogyaOS", "version": "0.1.0"},
        "implementation": {
            "description": "Read-only FHIR R4 export of the clinical record. Base resources "
            "only; no ABDM profile conformance is claimed. "
            "Custom read: GET Encounter/{id}/$export-document.",
            "url": base_url,
        },
        "fhirVersion": FHIR_VERSION,
        "format": ["json"],
        "rest": [
            {
                "mode": "server",
                "resource": [
                    {"type": "Patient", "interaction": [{"code": "read"}]},
                    {"type": "Encounter", "interaction": [{"code": "read"}]},
                ],
            }
        ],
    }
