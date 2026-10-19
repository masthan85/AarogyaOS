"""A cause/circumstance finding, and scheduling a follow-up from what the doctor said."""

import json
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.llm import LLMRequest, LLMResponse
from app.ai.registry import register, unregister
from app.modules.cover.service import today
from tests.ai_helpers import DOCTOR, PATIENT, ai_interaction, ai_visit, analyse, say
from tests.clinical_helpers import Visit, get, post

H = dict[str, str]
TALK = [
    (DOCTOR, "Hello, how are you today? Nice weather."),
    (PATIENT, "I fell from my bike three weeks ago and since then my lower back hurts."),
    (DOCTOR, "Take this medicine and come back after 5 days."),
    (DOCTOR, "Come back if it gets worse."),
]


class Scripted:
    """Answers with fixed candidates; the real guardrails still check them against the transcript."""

    name = "scripted"
    model = "scripted-1"
    is_development = True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        seg = {s["text"]: s["seq"] for s in request.payload["segments"]}
        cands = [
            {
                "kind": "CIRCUMSTANCE",
                "text": "Fell from a bike",
                "assertion": "PRESENT",
                "attributes": {
                    "event": "fall from a bike",
                    "when": "three weeks ago",
                    "bogus": "x",
                },
                "evidence": [
                    {"seq": seg[TALK[1][1]], "quote": "I fell from my bike three weeks ago"}
                ],
            },
            {
                "kind": "FOLLOW_UP",
                "text": "Return visit in 5 days",
                "assertion": "PRESENT",
                "attributes": {"when": "after 5 days"},
                "evidence": [{"seq": seg[TALK[2][1]], "quote": "come back after 5 days"}],
            },
            {
                "kind": "FOLLOW_UP",
                "text": "Return if worse",
                "assertion": "PRESENT",
                "attributes": {"when": "if it gets worse"},
                "evidence": [{"seq": seg[TALK[3][1]], "quote": "Come back if it gets worse"}],
            },
            {  # small talk that a careless model might return: nothing grounds it as a kind we allow
                "kind": "SOCIAL_HISTORY",
                "text": "Nice weather",
                "assertion": "PRESENT",
                "evidence": [{"seq": seg[TALK[0][1]], "quote": "Nice weather"}],
            },
        ]
        return LLMResponse(json.dumps({"candidates": cands}), 10, 10, 1)


@pytest.fixture
def scripted(client: TestClient) -> Iterator[None]:
    register("scripted", Scripted)
    client.app.state.settings.llm_provider = "scripted"  # type: ignore[attr-defined]
    yield
    unregister("scripted")


def run(client: TestClient, org_a: H, db: Session) -> tuple[Visit, str, list[dict[str, Any]]]:
    v = ai_visit(client, org_a)
    iid = ai_interaction(client, v)
    say(db, iid, TALK)
    assert analyse(client, v.doctor, iid).json()["status"] == "OK"
    found = get(client, v.doctor, f"/interactions/{iid}/ai/candidates").json()
    return v, iid, found


def by_kind(found: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [c for c in found if c["kind"] == kind]


def test_a_cause_is_kept_with_its_evidence_and_becomes_part_of_the_history_when_accepted(
    client: TestClient, org_a: H, db: Session, scripted: None
) -> None:
    v, _, found = run(client, org_a, db)
    (cause,) = by_kind(found, "CIRCUMSTANCE")
    assert cause["attributes"] == {"event": "fall from a bike", "when": "three weeks ago"}
    assert "unknown_attributes_removed" in cause["risk_flags"]
    r = post(client, v.doctor, f"/ai/candidates/{cause['id']}/review", {"action": "accept"})
    assert r.status_code == 200, r.text
    assert r.json()["result_kind"] == "clinical_notes"
    notes = get(client, v.doctor, f"/encounters/{v.enc_id}").json()["notes"]
    assert any(n["note_type"] == "HPI" and "Fell from a bike" in n["content"] for n in notes)
    # Small talk produced no cause; the model's social-history guess about the weather is still only a
    # candidate for a person to reject.
    assert not any("hello" in c["text"].lower() for c in found)


def test_a_stated_time_can_be_scheduled_as_a_follow_up_only_when_the_doctor_chooses(
    client: TestClient, org_a: H, db: Session, scripted: None
) -> None:
    v, _, found = run(client, org_a, db)
    five, vague = sorted(by_kind(found, "FOLLOW_UP"), key=lambda c: c["follow_up_in_days"] is None)
    assert five["follow_up_in_days"] == 5 and vague["follow_up_in_days"] is None
    # Accepting as a plain note schedules nothing.
    assert (
        post(
            client, v.doctor, f"/ai/candidates/{vague['id']}/review", {"action": "accept"}
        ).status_code
        == 200
    )
    assert get(client, v.doctor, "/follow-ups").json() == []
    # A time that cannot be read is refused rather than guessed.
    other = post(
        client,
        v.doctor,
        f"/ai/candidates/{five['id']}/review",
        {"action": "edit", "edited_text": "when it suits", "mode": "follow_up"},
    )
    assert other.status_code == 400
    r = post(
        client,
        v.doctor,
        f"/ai/candidates/{five['id']}/review",
        {"action": "accept", "mode": "follow_up"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["result_kind"] == "follow_ups"
    (fu,) = get(client, v.doctor, "/follow-ups").json()
    assert fu["due_date"] == str(today() + timedelta(days=5)) and fu["status"] == "PENDING"
    due = db.execute(text("select count(*) from follow_ups")).scalar()
    assert due == 1


def test_nurses_and_others_cannot_schedule_follow_ups_this_way(
    client: TestClient, org_a: H, db: Session, scripted: None
) -> None:
    v, _, found = run(client, org_a, db)
    five = next(c for c in by_kind(found, "FOLLOW_UP") if c["follow_up_in_days"])
    r = post(
        client,
        v.nurse,
        f"/ai/candidates/{five['id']}/review",
        {"action": "accept", "mode": "follow_up"},
    )
    assert r.status_code in (403, 404)
