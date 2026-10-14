import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import AppError, Forbidden, NotFound
from app.modules.audit.service import emit_event, record_audit
from app.modules.clinical import reference_ranges as rr
from app.modules.clinical.encounters import open_encounter, require_owner
from app.modules.clinical.facts import (
    current_filter,
    get_fact,
    provenance_for_new,
    supersede,
)
from app.modules.clinical.models import (
    Allergy,
    ClinicalNote,
    Condition,
    Encounter,
    InvestigationResult,
    Observation,
    PatientMedication,
)
from app.modules.clinical.schemas import (
    TRIAGE_NOTE_TYPES,
    AllergyEdit,
    AllergyIn,
    AllergyOut,
    ClinicalAlert,
    ClinicalState,
    ConditionEdit,
    ConditionIn,
    ConditionOut,
    EncounterOut,
    MedicationEdit,
    MedicationIn,
    MedicationOut,
    NoteEdit,
    NoteIn,
    NoteOut,
    ObservationCorrection,
    ObservationOut,
    ResultOut,
    VitalsIn,
)
from app.modules.patients.models import Patient
from app.modules.patients.normalise import age_years


def _name(code: str) -> str:
    return code.replace("_", " ").lower()


def _org(principal: Principal) -> uuid.UUID:
    assert principal.org_id is not None
    return principal.org_id


def _patient(session: Session, patient_id: uuid.UUID) -> Patient:
    p = session.get(Patient, patient_id)
    if p is None:
        raise NotFound("Patient not found")
    return p


def _record(
    session: Session,
    principal: Principal,
    kind: str,
    row: Any,
    event: str,
    extra: dict[str, object] | None = None,
) -> None:
    org_id = _org(principal)
    emit_event(
        session,
        org_id=org_id,
        event_type=event,
        aggregate_type=kind,
        aggregate_id=row.id,
        patient_id=row.patient_id,
        encounter_id=row.encounter_id,
        actor_user_id=principal.user_id,
        payload=extra,
    )
    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action=event,
        resource_type=kind,
        resource_id=row.id,
        after=extra,
    )


# ---- vitals ------------------------------------------------------------------------


def _vital_rows(body: VitalsIn) -> list[tuple[str, float, str | None, float | None, str | None]]:
    """(code, canonical value, context, original value, original unit)"""
    rows: list[tuple[str, float, str | None, float | None, str | None]] = []
    if body.temperature is not None:
        unit = (body.temperature.unit or "C").upper().replace("°", "")
        if unit not in ("C", "F"):
            raise AppError("Temperature unit must be C or F")
        if unit == "F":
            rows.append(
                (
                    "TEMPERATURE_C",
                    rr.fahrenheit_to_celsius(body.temperature.value),
                    None,
                    body.temperature.value,
                    "°F",
                )
            )
        else:
            rows.append(("TEMPERATURE_C", body.temperature.value, None, None, None))
    simple = {
        "SYSTOLIC_BP": body.systolic_bp,
        "DIASTOLIC_BP": body.diastolic_bp,
        "HEART_RATE": body.heart_rate,
        "RESPIRATORY_RATE": body.respiratory_rate,
        "SPO2": body.spo2,
        "HEIGHT_CM": body.height_cm,
        "WEIGHT_KG": body.weight_kg,
        "PAIN_SCORE": body.pain_score,
    }
    for code, value in simple.items():
        if value is not None:
            rows.append((code, value, None, None, None))
    if body.blood_glucose_mgdl is not None:
        rows.append(
            ("BLOOD_GLUCOSE", body.blood_glucose_mgdl, body.glucose_context or "RANDOM", None, None)
        )
    return rows


def record_vitals(
    session: Session, principal: Principal, encounter_id: uuid.UUID, body: VitalsIn
) -> list[ObservationOut]:
    enc = open_encounter(session, encounter_id)
    patient = _patient(session, enc.patient_id)
    age = age_years(patient.date_of_birth, date.today())
    rows = _vital_rows(body)
    if body.systolic_bp is not None and body.diastolic_bp is not None:
        if body.systolic_bp <= body.diastolic_bp:
            raise AppError("Systolic pressure must be higher than diastolic")
    now = datetime.now(UTC)
    created: list[Observation] = []
    for code, value, context, orig_value, orig_unit in rows:
        try:
            rr.check_plausible(code, value)
        except rr.ImplausibleValue as exc:
            raise AppError(str(exc)) from exc
        obs = Observation(
            organisation_id=_org(principal),
            patient_id=enc.patient_id,
            encounter_id=enc.id,
            code=code,
            value=Decimal(str(round(value, 2))),
            unit=rr.VITALS[code].unit,
            original_value=None if orig_value is None else Decimal(str(orig_value)),
            original_unit=orig_unit,
            context=context,
            observed_at=now,
            interpretation=rr.interpret(code, value, age, context),
            reference_version=rr.REFERENCE_VERSION,
            **provenance_for_new(principal, None),
        )
        session.add(obs)
        created.append(obs)
    session.flush()
    abnormal = sorted({o.code for o in created if o.interpretation in rr.ABNORMAL})
    _record(
        session,
        principal,
        "observations",
        created[0],
        "VITAL_RECORDED",
        {"codes": sorted(o.code for o in created), "abnormal": abnormal},
    )
    session.commit()
    return [ObservationOut.model_validate(o) for o in created]


def correct_observation(
    session: Session, principal: Principal, observation_id: uuid.UUID, body: ObservationCorrection
) -> ObservationOut:
    old = get_fact(session, Observation, observation_id)
    if old.encounter_id:
        open_encounter(session, old.encounter_id)
    value, orig_value, orig_unit = body.value, None, None
    if old.code == "TEMPERATURE_C" and (body.unit or "C").upper().replace("°", "") == "F":
        value, orig_value, orig_unit = (
            rr.fahrenheit_to_celsius(body.value),
            Decimal(str(body.value)),
            "°F",
        )
    try:
        rr.check_plausible(old.code, value)
    except rr.ImplausibleValue as exc:
        raise AppError(str(exc)) from exc
    patient = _patient(session, old.patient_id)
    new = supersede(
        session,
        principal,
        old,
        {
            "value": Decimal(str(round(value, 2))),
            "original_value": orig_value,
            "original_unit": orig_unit,
            "interpretation": rr.interpret(
                old.code, value, age_years(patient.date_of_birth, date.today()), old.context
            ),
            "reference_version": rr.REFERENCE_VERSION,
        },
    )
    _record(session, principal, "observations", new, "VITAL_CORRECTED", {"code": new.code})
    session.commit()
    return ObservationOut.model_validate(new)


# ---- notes -------------------------------------------------------------------------


def add_note(
    session: Session, principal: Principal, encounter_id: uuid.UUID, body: NoteIn
) -> NoteOut:
    enc = open_encounter(session, encounter_id)
    if body.note_type in TRIAGE_NOTE_TYPES:
        if not principal.has("note:triage"):
            raise Forbidden("You cannot write this type of note")
    else:
        if not principal.has("note:clinical"):
            raise Forbidden("Only the treating doctor writes this type of note")
        require_owner(session, principal, enc)
    note = ClinicalNote(
        organisation_id=_org(principal),
        patient_id=enc.patient_id,
        encounter_id=enc.id,
        note_type=body.note_type,
        content=body.content,
        **provenance_for_new(principal, body.source),
    )
    session.add(note)
    session.flush()
    _record(session, principal, "notes", note, "NOTE_RECORDED", {"type": body.note_type})
    session.commit()
    return NoteOut.model_validate(note)


def edit_note(
    session: Session, principal: Principal, note_id: uuid.UUID, body: NoteEdit
) -> NoteOut:
    old = get_fact(session, ClinicalNote, note_id)
    assert old.encounter_id is not None
    enc = open_encounter(session, old.encounter_id)
    if old.note_type in TRIAGE_NOTE_TYPES:
        if not principal.has("note:triage"):
            raise Forbidden("You cannot edit this note")
    else:
        if not principal.has("note:clinical"):
            raise Forbidden("Only the treating doctor edits this type of note")
        require_owner(session, principal, enc)
    new = supersede(session, principal, old, {"content": body.content.strip()})
    _record(session, principal, "notes", new, "NOTE_CORRECTED", {"type": new.note_type})
    session.commit()
    return NoteOut.model_validate(new)


# ---- conditions --------------------------------------------------------------------


def add_condition(
    session: Session, principal: Principal, encounter_id: uuid.UUID, body: ConditionIn
) -> ConditionOut:
    enc = open_encounter(session, encounter_id)
    require_owner(session, principal, enc)
    if body.certainty == "CONFIRMED" and not principal.has("condition:confirm"):
        raise Forbidden("Only a doctor can confirm a diagnosis")
    row = Condition(
        organisation_id=_org(principal),
        patient_id=enc.patient_id,
        encounter_id=enc.id,
        display=body.display.strip(),
        code=body.code,
        code_system=body.code_system,
        category=body.category,
        certainty=body.certainty,
        clinical_status=body.clinical_status,
        onset_date=body.onset_date,
        note=body.note,
        **provenance_for_new(principal, body.source),
    )
    session.add(row)
    session.flush()
    _record(
        session, principal, "conditions", row, "CONDITION_RECORDED", {"certainty": row.certainty}
    )
    if row.certainty == "CONFIRMED":
        _record(session, principal, "conditions", row, "DIAGNOSIS_CONFIRMED")
    session.commit()
    return ConditionOut.model_validate(row)


def edit_condition(
    session: Session, principal: Principal, condition_id: uuid.UUID, body: ConditionEdit
) -> ConditionOut:
    old = get_fact(session, Condition, condition_id)
    changes = body.model_dump(exclude_unset=True)
    confirming = changes.get("certainty") == "CONFIRMED" and old.certainty != "CONFIRMED"
    if confirming and not principal.has("condition:confirm"):
        raise Forbidden("Only a doctor can confirm a diagnosis")
    if not principal.has("condition:record"):
        raise Forbidden("Only a doctor can change diagnoses")
    new = supersede(session, principal, old, changes)
    _record(session, principal, "conditions", new, "CONDITION_CORRECTED")
    if confirming:
        _record(session, principal, "conditions", new, "DIAGNOSIS_CONFIRMED")
    session.commit()
    return ConditionOut.model_validate(new)


# ---- allergies ---------------------------------------------------------------------


def add_allergy(
    session: Session, principal: Principal, encounter_id: uuid.UUID, body: AllergyIn
) -> AllergyOut:
    enc = open_encounter(session, encounter_id)
    current = session.scalars(
        select(Allergy).where(
            Allergy.patient_id == enc.patient_id,
            *current_filter(Allergy),
            Allergy.clinical_status == "ACTIVE",
        )
    ).all()
    if body.is_nka and any(not a.is_nka for a in current):
        raise AppError(
            "This patient has recorded allergies; remove or resolve them before stating none"
        )
    if not body.is_nka:
        for nka in (a for a in current if a.is_nka):
            supersede(session, principal, nka, {"clinical_status": "INACTIVE"})
    row = Allergy(
        organisation_id=_org(principal),
        patient_id=enc.patient_id,
        encounter_id=enc.id,
        substance="No known allergies" if body.is_nka else body.substance.strip(),
        substance_code=body.code,
        code_system=body.code_system,
        category=body.category,
        reaction=body.reaction,
        severity="UNKNOWN" if body.is_nka else body.severity,
        certainty="CONFIRMED" if body.is_nka else body.certainty,
        is_nka=body.is_nka,
        **provenance_for_new(principal, body.source),
    )
    session.add(row)
    session.flush()
    _record(
        session,
        principal,
        "allergies",
        row,
        "ALLERGY_RECORDED",
        {"severity": row.severity, "certainty": row.certainty, "nka": row.is_nka},
    )
    session.commit()
    return AllergyOut.model_validate(row)


def edit_allergy(
    session: Session, principal: Principal, allergy_id: uuid.UUID, body: AllergyEdit
) -> AllergyOut:
    old = get_fact(session, Allergy, allergy_id)
    new = supersede(session, principal, old, body.model_dump(exclude_unset=True))
    _record(session, principal, "allergies", new, "ALLERGY_CORRECTED")
    session.commit()
    return AllergyOut.model_validate(new)


# ---- medication history ------------------------------------------------------------


def add_medication(
    session: Session, principal: Principal, encounter_id: uuid.UUID, body: MedicationIn
) -> MedicationOut:
    enc = open_encounter(session, encounter_id)
    row = PatientMedication(
        organisation_id=_org(principal),
        patient_id=enc.patient_id,
        encounter_id=enc.id,
        name=body.name.strip(),
        generic_name=body.generic_name,
        dose=body.dose,
        route=body.route,
        frequency=body.frequency,
        status=body.status,
        started_on=body.started_on,
        **provenance_for_new(principal, body.source),
    )
    session.add(row)
    session.flush()
    _record(session, principal, "medications", row, "MEDICATION_RECORDED")
    session.commit()
    return MedicationOut.model_validate(row)


def edit_medication(
    session: Session, principal: Principal, medication_id: uuid.UUID, body: MedicationEdit
) -> MedicationOut:
    old = get_fact(session, PatientMedication, medication_id)
    new = supersede(session, principal, old, body.model_dump(exclude_unset=True))
    _record(session, principal, "medications", new, "MEDICATION_CORRECTED")
    session.commit()
    return MedicationOut.model_validate(new)


# ---- aggregated clinical state -----------------------------------------------------


def _bmi(vitals: list[Observation]) -> float | None:
    height = next((v for v in vitals if v.code == "HEIGHT_CM"), None)
    weight = next((v for v in vitals if v.code == "WEIGHT_KG"), None)
    if not height or not weight:
        return None
    metres = float(height.value) / 100
    return round(float(weight.value) / (metres * metres), 1)


def clinical_state(session: Session, principal: Principal, patient_id: uuid.UUID) -> ClinicalState:
    patient = _patient(session, patient_id)
    allergies = list(
        session.scalars(
            select(Allergy)
            .where(
                Allergy.patient_id == patient_id,
                *current_filter(Allergy),
                Allergy.clinical_status == "ACTIVE",
            )
            .order_by(Allergy.recorded_at)
        )
    )
    conditions = list(
        session.scalars(
            select(Condition)
            .where(
                Condition.patient_id == patient_id,
                *current_filter(Condition),
                Condition.clinical_status == "ACTIVE",
            )
            .order_by(Condition.recorded_at)
        )
    )
    meds = list(
        session.scalars(
            select(PatientMedication).where(
                PatientMedication.patient_id == patient_id,
                *current_filter(PatientMedication),
                PatientMedication.status == "ACTIVE",
            )
        )
    )
    all_vitals = session.scalars(
        select(Observation)
        .where(Observation.patient_id == patient_id, *current_filter(Observation))
        .order_by(Observation.observed_at.desc())
    ).all()
    latest: dict[str, Observation] = {}
    for v in all_vitals:
        latest.setdefault(v.code, v)
    latest_list = sorted(latest.values(), key=lambda v: v.code)
    encounters = session.scalars(
        select(Encounter)
        .where(Encounter.patient_id == patient_id)
        .order_by(Encounter.started_at.desc())
        .limit(5)
    ).all()
    pending = session.scalars(
        select(InvestigationResult)
        .where(
            InvestigationResult.patient_id == patient_id, InvestigationResult.reviewed_at.is_(None)
        )
        .order_by(InvestigationResult.reported_at.desc())
    ).all()

    alerts: list[ClinicalAlert] = []
    real_allergies = [a for a in allergies if not a.is_nka]
    if not allergies:
        alerts.append(
            ClinicalAlert(
                level="WARNING",
                code="ALLERGY_STATUS_UNKNOWN",
                message="Allergy status has not been recorded.",
            )
        )
    for a in real_allergies:
        unconfirmed = a.certainty != "CONFIRMED" or a.verification_state in (
            "UNVERIFIED",
            "AI_GENERATED",
            "REQUIRES_REVIEW",
        )
        level = (
            "WARNING" if a.severity in ("SEVERE", "UNKNOWN", "MODERATE") or unconfirmed else "INFO"
        )
        qualifier = f"{a.severity.lower()}, " if a.severity != "UNKNOWN" else ""
        note = " (not yet verified by a clinician)" if unconfirmed else ""
        alerts.append(
            ClinicalAlert(
                level=level,
                code="ALLERGY",
                message=f"Allergy: {a.substance} ({qualifier}{a.certainty.lower()}){note}",
                ref_id=a.id,
            )
        )
    for v in latest_list:
        if v.interpretation in rr.CRITICAL:
            alerts.append(
                ClinicalAlert(
                    level="CRITICAL",
                    code="CRITICAL_VITAL",
                    ref_id=v.id,
                    message=f"Critical {_name(v.code)}: {v.value:g} {v.unit}",
                )
            )
        elif v.interpretation in rr.ABNORMAL:
            alerts.append(
                ClinicalAlert(
                    level="WARNING",
                    code="ABNORMAL_VITAL",
                    ref_id=v.id,
                    message=f"{v.interpretation.title()} {_name(v.code)}: {v.value:g} {v.unit}",
                )
            )
    for r in pending:
        if r.interpretation in rr.ABNORMAL:
            level = "CRITICAL" if r.interpretation in rr.CRITICAL else "WARNING"
            alerts.append(
                ClinicalAlert(
                    level=level,
                    code="RESULT_REVIEW",
                    ref_id=r.id,
                    message=f"Unreviewed {_name(r.interpretation)} result: {r.test_name}",
                )
            )
    age = age_years(patient.date_of_birth, date.today())
    if age is not None and age < rr.ADULT_FROM_AGE and latest_list:
        alerts.append(
            ClinicalAlert(
                level="INFO",
                code="PAEDIATRIC_RANGES",
                message="Vital-sign ranges for children are not configured; interpret clinically.",
            )
        )
    order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    alerts.sort(key=lambda a: order[a.level])

    record_audit(
        session,
        principal.meta,
        org_id=_org(principal),
        actor_user_id=principal.user_id,
        action="CLINICAL_STATE_VIEWED",
        resource_type="patient",
        resource_id=patient_id,
    )
    session.commit()
    return ClinicalState(
        patient_id=patient_id,
        allergies=[AllergyOut.model_validate(a) for a in allergies],
        allergy_status_recorded=bool(allergies),
        conditions=[ConditionOut.model_validate(c) for c in conditions],
        medications=[MedicationOut.model_validate(m) for m in meds],
        latest_vitals=[ObservationOut.model_validate(v) for v in latest_list],
        bmi=_bmi(latest_list),
        recent_encounters=[EncounterOut.model_validate(e) for e in encounters],
        results_awaiting_review=[ResultOut.model_validate(r) for r in pending],
        alerts=alerts,
        generated_at=datetime.now(UTC),
    )


def patient_vitals_history(
    session: Session, patient_id: uuid.UUID, code: str
) -> list[ObservationOut]:
    get_enc = session.scalars(
        select(Observation)
        .where(
            Observation.patient_id == patient_id,
            Observation.code == code,
            *current_filter(Observation),
        )
        .order_by(Observation.observed_at.desc())
        .limit(50)
    ).all()
    return [ObservationOut.model_validate(o) for o in get_enc]
