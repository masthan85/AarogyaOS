"""Deterministic prescription safety checks. No LLM is involved, and nothing here pretends to be
a drug database.

What this DOES check, conservatively and by plain text:
  * allergy status never recorded (cannot rule an allergy out),
  * a documented allergy (confirmed, possible, historical or unverified) whose name overlaps a
    prescribed medicine's name,
  * the same medicine twice in one prescription, or already on the patient's active medicines.

What it CANNOT check without a licensed medication knowledge provider (listed on every result so
that "no warnings" is never read as "safe"):
"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.clinical.facts import current_filter
from app.modules.clinical.models import Allergy, PatientMedication, PrescriptionItem
from app.modules.clinical.schemas import SafetyCheckOut, SafetyWarning

NOT_PERFORMED = [
    "Drug-drug interactions",
    "Contraindications for this patient",
    "Dose range, age, renal and hepatic dose adjustment",
    "Drug-class cross-sensitivity (for example penicillins and related antibiotics)",
]

_STRIP = re.compile(r"\b\d+(\.\d+)?\s*(mg|mcg|g|ml|iu|%)?\b|[^a-z\s]")


def _words(*texts: str | None) -> set[str]:
    out: set[str] = set()
    for text in texts:
        if not text:
            continue
        cleaned = _STRIP.sub(" ", text.lower())
        out.update(w for w in cleaned.split() if len(w) >= 4)
    return out


def _same_substance(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    x, y = " ".join(_words(a)), " ".join(_words(b))
    return bool(x) and bool(y) and (x == y or x in y or y in x)


def check_prescription(
    session: Session, patient_id: uuid.UUID, items: list[PrescriptionItem]
) -> SafetyCheckOut:
    warnings: list[SafetyWarning] = []
    allergies = list(
        session.scalars(
            select(Allergy).where(
                Allergy.patient_id == patient_id,
                *current_filter(Allergy),
                Allergy.clinical_status == "ACTIVE",
            )
        )
    )
    if not allergies:
        warnings.append(
            SafetyWarning(
                code="ALLERGY_STATUS_UNKNOWN",
                level="WARNING",
                message="Allergy status has not been recorded. Ask the patient before prescribing.",
            )
        )
    named = [a for a in allergies if not a.is_nka]
    meds = list(
        session.scalars(
            select(PatientMedication).where(
                PatientMedication.patient_id == patient_id,
                *current_filter(PatientMedication),
                PatientMedication.status == "ACTIVE",
            )
        )
    )
    for item in items:
        names = _words(item.medicine_name, item.generic_name, item.brand_name)
        for a in named:
            allergy_words = _words(a.substance)
            if names & allergy_words or any(
                _same_substance(a.substance, n)
                for n in (item.medicine_name, item.generic_name, item.brand_name)
            ):
                state = (
                    "documented" if a.verification_state == "CLINICIAN_CONFIRMED" else "unverified"
                )
                warnings.append(
                    SafetyWarning(
                        code=f"ALLERGY_MATCH:{item.position}:{a.id}",
                        level="WARNING",
                        position=item.position,
                        message=(
                            f"{item.medicine_name} may match a {state} "
                            f"{a.certainty.lower()} allergy to {a.substance}. "
                            "This is a name match only."
                        ),
                    )
                )
        for other in items:
            if other.position > item.position and (
                _same_substance(
                    item.generic_name or item.medicine_name,
                    other.generic_name or other.medicine_name,
                )
            ):
                warnings.append(
                    SafetyWarning(
                        code=f"DUPLICATE_IN_PRESCRIPTION:{item.position}:{other.position}",
                        level="WARNING",
                        position=other.position,
                        message=f"{other.medicine_name} appears twice in this prescription",
                    )
                )
        for m in meds:
            if _same_substance(item.generic_name or item.medicine_name, m.generic_name or m.name):
                warnings.append(
                    SafetyWarning(
                        code=f"DUPLICATE_THERAPY:{item.position}:{m.id}",
                        level="WARNING",
                        position=item.position,
                        message=f"The patient already takes {m.name}. Check for duplication.",
                    )
                )
    warnings.append(
        SafetyWarning(
            code="CHECKS_LIMITED",
            level="INFO",
            message="No medication knowledge provider is connected: "
            + "; ".join(NOT_PERFORMED).lower()
            + " were NOT checked.",
        )
    )
    return SafetyCheckOut(warnings=warnings, checks_not_performed=NOT_PERFORMED)
