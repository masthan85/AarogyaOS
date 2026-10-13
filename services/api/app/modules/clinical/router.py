import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core.context import Principal
from app.core.deps import TenantDb, require
from app.modules.clinical import encounters, orders, records
from app.modules.clinical.facts import verify_fact
from app.modules.clinical.models import Encounter
from app.modules.clinical.schemas import (
    AllergyEdit,
    AllergyIn,
    AllergyOut,
    CancelOrderIn,
    ClinicalState,
    ConditionEdit,
    ConditionIn,
    ConditionOut,
    EncounterDetail,
    EncounterOut,
    EncounterStart,
    FollowUpIn,
    FollowUpOut,
    FollowUpStatusIn,
    MedicationEdit,
    MedicationIn,
    MedicationOut,
    NoteEdit,
    NoteIn,
    NoteOut,
    ObservationCorrection,
    ObservationOut,
    PrescriptionIn,
    PrescriptionOut,
    ResultIn,
    ResultOut,
    SafetyCheckOut,
    ServiceRequestIn,
    ServiceRequestOut,
    SignIn,
    TriageCategoryIn,
    VerifyIn,
    VitalsIn,
    VoidIn,
)

router = APIRouter(tags=["clinical"])


# ---- encounters --------------------------------------------------------------------


@router.post("/encounters/triage", response_model=EncounterOut)
def start_triage(
    body: EncounterStart,
    response: Response,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("encounter:triage"))],
) -> Encounter:
    enc, created = encounters.start_triage(db, principal, body.appointment_id)
    response.status_code = 201 if created else 200
    return enc


@router.post("/encounters/consultation", response_model=EncounterOut)
def start_consultation(
    body: EncounterStart,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("encounter:consult"))],
) -> Encounter:
    return encounters.start_consultation(db, principal, body.appointment_id)


@router.get("/encounters/{encounter_id}", response_model=EncounterDetail)
def get_encounter(
    encounter_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("encounter:read"))],
) -> EncounterDetail:
    return encounters.detail(db, principal, encounter_id)


@router.put("/encounters/{encounter_id}/triage-category", response_model=EncounterOut)
def set_triage_category(
    encounter_id: uuid.UUID,
    body: TriageCategoryIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("encounter:triage"))],
) -> Encounter:
    return encounters.set_triage_category(db, principal, encounter_id, body.category)


@router.post("/encounters/{encounter_id}/complete", response_model=EncounterOut)
def complete_encounter(
    encounter_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("encounter:consult"))],
) -> Encounter:
    return encounters.complete(db, principal, encounter_id)


@router.get("/patients/{patient_id}/encounters", response_model=list[EncounterOut])
def patient_encounters(
    patient_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("encounter:read"))],
) -> list[Encounter]:
    return encounters.list_for_patient(db, principal, patient_id)


# ---- facts -------------------------------------------------------------------------

ReadEnc = Annotated[Principal, Depends(require("encounter:read"))]


@router.post(
    "/encounters/{encounter_id}/vitals", response_model=list[ObservationOut], status_code=201
)
def record_vitals(
    encounter_id: uuid.UUID,
    body: VitalsIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("vitals:record"))],
) -> list[ObservationOut]:
    return records.record_vitals(db, principal, encounter_id, body)


@router.put("/observations/{observation_id}", response_model=ObservationOut)
def correct_observation(
    observation_id: uuid.UUID,
    body: ObservationCorrection,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("vitals:record"))],
) -> ObservationOut:
    return records.correct_observation(db, principal, observation_id, body)


@router.get("/patients/{patient_id}/vitals", response_model=list[ObservationOut])
def vitals_history(
    patient_id: uuid.UUID,
    code: Annotated[str, Query(max_length=30)],
    db: TenantDb,
    _: Annotated[Principal, Depends(require("patient:clinical"))],
) -> list[ObservationOut]:
    return records.patient_vitals_history(db, patient_id, code.upper())


@router.post("/encounters/{encounter_id}/notes", response_model=NoteOut, status_code=201)
def add_note(encounter_id: uuid.UUID, body: NoteIn, db: TenantDb, principal: ReadEnc) -> NoteOut:
    return records.add_note(db, principal, encounter_id, body)


@router.put("/notes/{note_id}", response_model=NoteOut)
def edit_note(note_id: uuid.UUID, body: NoteEdit, db: TenantDb, principal: ReadEnc) -> NoteOut:
    return records.edit_note(db, principal, note_id, body)


@router.post("/encounters/{encounter_id}/conditions", response_model=ConditionOut, status_code=201)
def add_condition(
    encounter_id: uuid.UUID,
    body: ConditionIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("condition:record"))],
) -> ConditionOut:
    return records.add_condition(db, principal, encounter_id, body)


@router.put("/conditions/{condition_id}", response_model=ConditionOut)
def edit_condition(
    condition_id: uuid.UUID,
    body: ConditionEdit,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("condition:record"))],
) -> ConditionOut:
    return records.edit_condition(db, principal, condition_id, body)


@router.post("/encounters/{encounter_id}/allergies", response_model=AllergyOut, status_code=201)
def add_allergy(
    encounter_id: uuid.UUID,
    body: AllergyIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("allergy:record"))],
) -> AllergyOut:
    return records.add_allergy(db, principal, encounter_id, body)


@router.put("/allergies/{allergy_id}", response_model=AllergyOut)
def edit_allergy(
    allergy_id: uuid.UUID,
    body: AllergyEdit,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("allergy:record"))],
) -> AllergyOut:
    return records.edit_allergy(db, principal, allergy_id, body)


@router.post(
    "/encounters/{encounter_id}/medications", response_model=MedicationOut, status_code=201
)
def add_medication(
    encounter_id: uuid.UUID,
    body: MedicationIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("medication:record"))],
) -> MedicationOut:
    return records.add_medication(db, principal, encounter_id, body)


@router.put("/medications/{medication_id}", response_model=MedicationOut)
def edit_medication(
    medication_id: uuid.UUID,
    body: MedicationEdit,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("medication:record"))],
) -> MedicationOut:
    return records.edit_medication(db, principal, medication_id, body)


@router.post("/clinical/{kind}/{fact_id}/verify", response_model=dict[str, str])
def verify(
    kind: str,
    fact_id: uuid.UUID,
    body: VerifyIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("fact:verify"))],
) -> dict[str, str]:
    row = verify_fact(db, principal, kind, fact_id, body.action, body.reason)
    db.commit()
    return {"id": str(row.id), "verification_state": row.verification_state}


@router.get("/patients/{patient_id}/clinical-state", response_model=ClinicalState)
def clinical_state(
    patient_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("patient:clinical"))],
) -> ClinicalState:
    return records.clinical_state(db, principal, patient_id)


# ---- prescriptions -----------------------------------------------------------------

RxWrite = Annotated[Principal, Depends(require("prescription:write"))]


@router.post(
    "/encounters/{encounter_id}/prescriptions", response_model=PrescriptionOut, status_code=201
)
def create_prescription(
    encounter_id: uuid.UUID, body: PrescriptionIn, db: TenantDb, principal: RxWrite
) -> PrescriptionOut:
    return orders.create_prescription(db, principal, encounter_id, body)


@router.put("/prescriptions/{rx_id}", response_model=PrescriptionOut)
def update_prescription(
    rx_id: uuid.UUID, body: PrescriptionIn, db: TenantDb, principal: RxWrite
) -> PrescriptionOut:
    return orders.update_prescription(db, principal, rx_id, body)


@router.get("/prescriptions/{rx_id}", response_model=PrescriptionOut)
def get_prescription(
    rx_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("prescription:read"))],
) -> PrescriptionOut:
    return orders.get_prescription(db, principal, rx_id)


@router.post("/prescriptions/{rx_id}/safety-check", response_model=SafetyCheckOut)
def safety_check(rx_id: uuid.UUID, db: TenantDb, principal: RxWrite) -> SafetyCheckOut:
    return orders.safety_check(db, principal, rx_id)


@router.post("/prescriptions/{rx_id}/sign", response_model=PrescriptionOut)
def sign_prescription(
    rx_id: uuid.UUID,
    body: SignIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("prescription:sign"))],
) -> PrescriptionOut:
    return orders.sign_prescription(db, principal, rx_id, body.acknowledged_warning_codes)


@router.post("/prescriptions/{rx_id}/void", response_model=PrescriptionOut)
def void_prescription(
    rx_id: uuid.UUID, body: VoidIn, db: TenantDb, principal: RxWrite
) -> PrescriptionOut:
    return orders.void_prescription(db, principal, rx_id, body.reason)


@router.get("/patients/{patient_id}/prescriptions", response_model=list[PrescriptionOut])
def patient_prescriptions(
    patient_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("prescription:read"))],
) -> list[PrescriptionOut]:
    return orders.patient_prescriptions(db, principal, patient_id)


# ---- investigations ----------------------------------------------------------------

OrderWrite = Annotated[Principal, Depends(require("order:write"))]


@router.post("/encounters/{encounter_id}/orders", response_model=ServiceRequestOut, status_code=201)
def create_order(
    encounter_id: uuid.UUID, body: ServiceRequestIn, db: TenantDb, principal: OrderWrite
) -> ServiceRequestOut:
    return orders.create_order(db, principal, encounter_id, body)


@router.post("/orders/{order_id}/place", response_model=ServiceRequestOut)
def place_order(order_id: uuid.UUID, db: TenantDb, principal: OrderWrite) -> ServiceRequestOut:
    return orders.place_order(db, principal, order_id)


@router.post("/orders/{order_id}/cancel", response_model=ServiceRequestOut)
def cancel_order(
    order_id: uuid.UUID, body: CancelOrderIn, db: TenantDb, principal: OrderWrite
) -> ServiceRequestOut:
    return orders.cancel_order(db, principal, order_id, body.reason)


@router.get("/orders", response_model=list[ServiceRequestOut])
def list_orders(
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("order:read"))],
    encounter_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    category: Annotated[str | None, Query(max_length=10)] = None,
    status: Annotated[str | None, Query(max_length=10)] = None,
) -> list[ServiceRequestOut]:
    return orders.list_orders(
        db,
        principal,
        encounter_id=encounter_id,
        patient_id=patient_id,
        category=category,
        status=status,
    )


@router.post("/orders/{order_id}/results", response_model=ResultOut, status_code=201)
def enter_result(
    order_id: uuid.UUID,
    body: ResultIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("result:enter"))],
) -> ResultOut:
    return orders.enter_result(db, principal, order_id, body)


@router.get("/results/awaiting-review", response_model=list[ResultOut])
def awaiting_review(
    db: TenantDb, principal: Annotated[Principal, Depends(require("result:review"))]
) -> list[ResultOut]:
    return orders.results_awaiting_review(db, principal)


@router.post("/results/{result_id}/review", response_model=ResultOut)
def review_result(
    result_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("result:review"))],
) -> ResultOut:
    return orders.review_result(db, principal, result_id)


@router.get("/patients/{patient_id}/results", response_model=list[ResultOut])
def patient_results(
    patient_id: uuid.UUID,
    db: TenantDb,
    _: Annotated[Principal, Depends(require("patient:clinical"))],
) -> list[ResultOut]:
    return orders.patient_results(db, patient_id)


# ---- follow-ups --------------------------------------------------------------------


@router.post("/encounters/{encounter_id}/follow-ups", response_model=FollowUpOut, status_code=201)
def create_followup(
    encounter_id: uuid.UUID,
    body: FollowUpIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("followup:write"))],
) -> FollowUpOut:
    return orders.create_followup(db, principal, encounter_id, body)


@router.get("/follow-ups", response_model=list[FollowUpOut])
def list_followups(
    db: TenantDb,
    _: Annotated[Principal, Depends(require("followup:read"))],
    patient_id: uuid.UUID | None = None,
    due_on_or_before: date | None = None,
    status: Annotated[str | None, Query(max_length=10)] = None,
) -> list[FollowUpOut]:
    return orders.list_followups(
        db, patient_id=patient_id, due_on_or_before=due_on_or_before, status=status
    )


@router.post("/follow-ups/{followup_id}/status", response_model=FollowUpOut)
def set_followup_status(
    followup_id: uuid.UUID,
    body: FollowUpStatusIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("followup:write"))],
) -> FollowUpOut:
    return orders.set_followup_status(db, principal, followup_id, body.status)
