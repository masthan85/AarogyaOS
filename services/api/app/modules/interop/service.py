"""Builds FHIR resources from the record for authorised, audited, read-only export.

This is an internal export for the organisation's own authorised users. It sends nothing to anyone:
sharing with another provider or with ABDM needs the patient's consent artefact and an approved
channel, which Phase 6 does not build.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import Conflict, NotFound
from app.modules.audit.service import record_audit
from app.modules.clinical.encounters import get_encounter, require_owner
from app.modules.clinical.models import (
    Allergy,
    ClinicalNote,
    Condition,
    InvestigationResult,
    Observation,
    PatientMedication,
    Prescription,
    PrescriptionItem,
    ServiceRequest,
)
from app.modules.identity.models import User
from app.modules.interop import fhir
from app.modules.patients.models import Patient
from app.modules.scheduling.models import Practitioner
from app.modules.tenancy.models import Facility


def _audit(session: Session, principal: Principal, action: str, rtype: str, rid: uuid.UUID) -> None:
    assert principal.org_id is not None
    record_audit(
        session,
        principal.meta,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        action=action,
        resource_type=rtype,
        resource_id=rid,
    )
    session.commit()


def patient_resource(
    session: Session, principal: Principal, patient_id: uuid.UUID
) -> dict[str, object]:
    p = session.get(Patient, patient_id)
    if p is None:
        raise NotFound("Patient not found")
    out = fhir.patient(p)
    _audit(session, principal, "FHIR_PATIENT_EXPORTED", "patient", p.id)
    return out


def encounter_resource(
    session: Session, principal: Principal, encounter_id: uuid.UUID
) -> dict[str, object]:
    enc = get_encounter(session, encounter_id)
    require_owner(session, principal, enc)
    out = fhir.encounter(enc)
    _audit(session, principal, "FHIR_ENCOUNTER_EXPORTED", "encounter", enc.id)
    return out


def encounter_document(
    session: Session, principal: Principal, encounter_id: uuid.UUID
) -> dict[str, object]:
    enc = get_encounter(session, encounter_id)
    require_owner(session, principal, enc)
    if enc.status != "COMPLETED":
        raise Conflict("Only a completed visit can be exported as a document")
    if enc.practitioner_id is None:
        raise Conflict("The visit has no responsible practitioner")
    pid = enc.patient_id
    pat = session.get(Patient, pid)
    prac = session.get(Practitioner, enc.practitioner_id)
    facility = session.get(Facility, enc.facility_id)
    if pat is None or prac is None or facility is None:
        raise NotFound("Visit data is incomplete")
    user = session.get(User, prac.user_id)

    def settled(model: type, *extra: object) -> list:  # type: ignore[type-arg]
        return list(
            session.scalars(
                select(model).where(
                    model.is_current.is_(True),  # type: ignore[attr-defined]
                    model.verification_state != "CLINICIAN_REJECTED",  # type: ignore[attr-defined]
                    *extra,  # type: ignore[arg-type]
                )
            )
        )

    notes = settled(ClinicalNote, ClinicalNote.encounter_id == enc.id)
    observations = settled(Observation, Observation.encounter_id == enc.id)
    conditions = settled(Condition, Condition.encounter_id == enc.id)
    allergies = settled(Allergy, Allergy.patient_id == pid)
    medicines = settled(
        PatientMedication, PatientMedication.patient_id == pid, PatientMedication.status == "ACTIVE"
    )
    requests = [
        r
        for r in session.scalars(
            select(ServiceRequest).where(ServiceRequest.encounter_id == enc.id)
        )
        if r.status in ("ORDERED", "RESULTED", "CANCELLED")  # drafts never leave
    ]
    results = list(
        session.scalars(
            select(InvestigationResult).where(
                InvestigationResult.service_request_id.in_([r.id for r in requests])
            )
        )
    )
    signed = list(
        session.scalars(
            select(Prescription).where(
                Prescription.encounter_id == enc.id, Prescription.status == "SIGNED"
            )
        )
    )

    author = fhir.ref("Practitioner", prac.id)
    resources: list[dict[str, object]] = [
        fhir.patient(pat),
        fhir.practitioner(prac, user.full_name if user else "Practitioner"),
        fhir.organisation(facility),
        fhir.encounter(enc),
    ]
    refs: dict[str, list[dict[str, str]]] = {}

    def add(rtype: str, resource: dict[str, object]) -> None:
        if resource:
            resources.append(resource)
            refs.setdefault(rtype, []).append(fhir.ref(rtype, str(resource["id"])))

    for o in observations:
        add("Observation", fhir.vital(o))
    for r in results:
        add("Observation", fhir.lab_result(r, enc.id, pid))
    for c in conditions:
        add("Condition", fhir.condition(c))
    for a in allergies:
        add("AllergyIntolerance", fhir.allergy(a))
    for m in medicines:
        add("MedicationStatement", fhir.medication_statement(m))
    for sr in requests:
        add("ServiceRequest", fhir.service_request(sr))
    for rx in signed:
        for item in session.scalars(
            select(PrescriptionItem)
            .where(PrescriptionItem.prescription_id == rx.id)
            .order_by(PrescriptionItem.position)
        ):
            add("MedicationRequest", fhir.medication_request(rx, item, author))

    comp = fhir.composition(
        enc,
        patient_ref=fhir.ref("Patient", pid),
        author=author,
        custodian=fhir.ref("Organization", facility.id),
        notes=notes,
        sections_refs=refs,
        no_known_allergies=any(a.is_nka for a in allergies),
    )
    bundle = fhir.document_bundle(comp, resources)
    _audit(session, principal, "FHIR_DOCUMENT_EXPORTED", "encounter", enc.id)
    return bundle
