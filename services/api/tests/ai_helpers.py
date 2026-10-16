"""Builders for clinical-AI tests: a consented AI session with a hand-written transcript."""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import set_tenant
from app.modules.interactions.models import InteractionSpeaker, TranscriptSegment
from tests.clinical_helpers import Visit, post
from tests.speech_helpers import recording_ready

PATIENT, DOCTOR = "S1", "S2"


def ai_visit(client: TestClient, admin: dict[str, str], *, suggestions: bool = False) -> Visit:
    v = recording_ready(client, admin, ai=True)
    body = {
        "recording_enabled": True,
        "ai_processing_enabled": True,
        "ai_suggestions_enabled": suggestions,
    }
    r = client.put("/api/v1/organisations/current/policy", headers=admin, json=body)
    assert r.status_code == 200, r.text
    return v


def ai_interaction(client: TestClient, v: Visit) -> str:
    r = post(
        client,
        v.doctor,
        "/interactions",
        {
            "patient_id": v.patient["id"],
            "purpose": "CONSULTATION",
            "encounter_id": v.enc_id,
            "ai_processing": True,
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def say(db: Session, iid: str, lines: list[tuple[str, str]], *, start_seq: int = 1) -> list[str]:
    """Insert final transcript segments (speaker id, text) as the speech pipeline would."""
    from app.modules.interactions.models import ClinicalInteraction

    set_tenant(db, None, bypass=True)
    ia = db.get(ClinicalInteraction, uuid.UUID(iid))
    assert ia is not None
    for sid, role in ((PATIENT, "PATIENT"), (DOCTOR, "DOCTOR")):
        if db.get(InteractionSpeaker, (ia.id, sid)) is None:
            db.add(
                InteractionSpeaker(
                    interaction_id=ia.id,
                    speaker_id=sid,
                    organisation_id=ia.organisation_id,
                    role=role,
                )
            )
    segs = []
    for i, (sid, text) in enumerate(lines):
        seg = TranscriptSegment(
            organisation_id=ia.organisation_id,
            interaction_id=ia.id,
            patient_id=ia.patient_id,
            seq=start_seq + i,
            speaker_id=sid,
            start_ms=i * 2000,
            end_ms=i * 2000 + 1900,
            raw_text=text,
            provider="development",
            provider_model="dev-1",
        )
        db.add(seg)
        segs.append(seg)
    db.commit()
    return [str(s.id) for s in segs]


def analyse(client: TestClient, h: dict[str, str], iid: str) -> Any:
    return post(client, h, f"/interactions/{iid}/ai/analyse")
