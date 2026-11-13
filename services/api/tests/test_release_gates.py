"""Safeguards that stand between a working build and a pilot: repeated requests, provider approval,
one live instance, restart handling, usage allowances and the audio socket's origin check."""

import threading
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import create_db_engine, set_tenant
from app.core.instance import InstanceLock
from app.jobs import purge_idempotency_keys
from app.main import create_app
from app.modules.interactions.models import ClinicalInteraction, SpeechUsage
from tests.ai_helpers import ai_interaction, ai_visit, analyse, say
from tests.clinical_helpers import Visit, get, post
from tests.speech_helpers import (
    create_session,
    put,
    recording_ready,
    start_session,
    token_of,
)
from tests.test_billing import billing, issued, v  # noqa: F401  (fixtures)

H = dict[str, str]
STRONG = {
    "environment": "production",
    "jwt_secret": "s" * 40,
    "field_encryption_key": "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=",
    "database_url": "postgresql+psycopg://app:long-password@db.internal:5432/aarogya",
}


def pay(client: TestClient, h: H, invoice_id: str, amount: int, key: str | None) -> Any:
    headers = {**h, "Idempotency-Key": key} if key else h
    return client.post(
        f"/api/v1/invoices/{invoice_id}/payments",
        headers=headers,
        json={"amount_paise": amount, "method": "CASH"},
    )


# --- repeated requests ---------------------------------------------------------------------


def test_a_payment_sent_twice_with_the_same_key_is_recorded_once(
    client: TestClient,
    v: Visit,  # noqa: F811
    billing: H,  # noqa: F811
) -> None:
    inv = issued(client, billing, v)
    key = "pay-" + uuid.uuid4().hex
    first = pay(client, billing, inv["id"], 10000, key)
    again = pay(client, billing, inv["id"], 10000, key)
    assert first.status_code == 201 and again.status_code == 201
    assert len(again.json()["payments"]) == 1
    assert again.json()["balance_paise"] == first.json()["balance_paise"]

    # A different key is a different payment, and no key keeps the old behaviour.
    assert (
        len(pay(client, billing, inv["id"], 10000, "pay-" + uuid.uuid4().hex).json()["payments"])
        == 2
    )
    assert len(pay(client, billing, inv["id"], 10000, None).json()["payments"]) == 3


def test_two_identical_payments_racing_each_other_still_make_one(
    client: TestClient,
    v: Visit,  # noqa: F811
    billing: H,  # noqa: F811
) -> None:
    inv = issued(client, billing, v)
    key = "race-" + uuid.uuid4().hex
    codes: list[int] = []

    def send() -> None:
        codes.append(pay(client, billing, inv["id"], 5000, key).status_code)

    threads = [threading.Thread(target=send) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert codes == [201] * 4
    assert len(get(client, billing, f"/invoices/{inv['id']}").json()["payments"]) == 1


def test_a_refused_payment_does_not_use_up_its_key(
    client: TestClient,
    v: Visit,  # noqa: F811
    billing: H,  # noqa: F811
) -> None:
    inv = issued(client, billing, v)
    key = "retry-" + uuid.uuid4().hex
    too_much = pay(client, billing, inv["id"], inv["total_paise"] + 1, key)
    assert too_much.status_code == 409
    ok = pay(client, billing, inv["id"], 5000, key)  # the corrected request may reuse the key
    assert ok.status_code == 201 and len(ok.json()["payments"]) == 1


def test_keys_are_private_to_an_organisation_and_old_ones_are_purged(
    client: TestClient,
    v: Visit,  # noqa: F811
    billing: H,  # noqa: F811
    db: Session,
    settings: Settings,
) -> None:
    inv = issued(client, billing, v)
    assert pay(client, billing, inv["id"], 5000, "shared-key-0001").status_code == 201
    assert db.scalar(text("select count(*) from idempotency_keys")) == 1
    # Row-level security: with another organisation's context the key cannot be seen at all.
    with client.app.state.sessionmaker() as other:  # type: ignore[attr-defined]
        set_tenant(other, uuid.uuid4())
        assert other.scalar(text("select count(*) from idempotency_keys")) == 0
    assert purge_idempotency_keys(db, settings) == {"deleted": 0}
    db.execute(text("update idempotency_keys set created_at = now() - interval '3 days'"))
    db.commit()
    assert purge_idempotency_keys(db, settings) == {"deleted": 1}


# --- provider approval ---------------------------------------------------------------------


def test_production_refuses_a_provider_that_is_not_on_the_approved_list() -> None:
    with pytest.raises(ValidationError, match="AAROGYA_SPEECH_PROVIDER=sarvam"):
        Settings(**STRONG, speech_provider="sarvam")  # type: ignore[arg-type]
    # The fallback is a provider too: it cannot slip in unapproved behind an approved primary.
    with pytest.raises(ValidationError, match="AAROGYA_SPEECH_FALLBACK_PROVIDER=deepgram"):
        Settings(  # type: ignore[arg-type]
            **STRONG,
            speech_provider="sarvam",
            speech_fallback_provider="deepgram",
            patient_data_providers=["sarvam"],
        )
    with pytest.raises(ValidationError, match="AAROGYA_LLM_PROVIDER=anthropic"):
        Settings(**STRONG, llm_provider="anthropic", patient_data_providers=["sarvam"])  # type: ignore[arg-type]

    ok = Settings(  # type: ignore[arg-type]
        **STRONG,
        speech_provider="sarvam",
        llm_provider="Sarvam",
        translation_provider="sarvam",
        patient_data_providers=["sarvam"],
    )
    assert ok.external_providers() == {
        "speech_provider": "sarvam",
        "llm_provider": "sarvam",
        "translation_provider": "sarvam",
    }
    # With nothing configured there is nothing to approve: the product runs by hand.
    assert Settings(**STRONG).external_providers() == {}  # type: ignore[arg-type]


def test_the_single_instance_guard_is_on_in_production_and_off_in_development() -> None:
    assert Settings(**STRONG).single_instance_guard is True  # type: ignore[arg-type]
    assert Settings(environment="development").single_instance_guard is False
    assert Settings(environment="development", single_instance_guard=True).single_instance_guard


# --- one live instance ---------------------------------------------------------------------


def test_only_one_process_can_hold_the_instance_lock(settings: Settings) -> None:
    engine = create_db_engine(settings.database_url)
    first, second = InstanceLock(engine), InstanceLock(engine)
    try:
        assert first.acquire() and first.held()
        assert first.acquire()  # asking again is harmless
        assert not second.acquire() and not second.held()
        first.release()  # the active process stops: the lock goes with its connection
        assert second.held()
        assert not first.acquire()
    finally:
        first.release()
        second.release()
        engine.dispose()


def test_a_second_instance_reports_standby_and_refuses_audio(settings: Settings) -> None:
    guarded = settings.model_copy(update={"single_instance_guard": True})
    active_app, standby_app = create_app(guarded), create_app(guarded)
    try:
        with TestClient(active_app) as active, TestClient(standby_app) as standby:
            ready = active.get("/ready")
            assert ready.status_code == 200, ready.text
            waiting = standby.get("/ready")
            assert waiting.status_code == 503 and waiting.json() == {"status": "standby"}
            assert standby.get("/health").status_code == 200  # alive, just not in rotation
            with standby.websocket_connect(f"/api/v1/interactions/{uuid.uuid4()}/audio") as ws:
                assert ws.receive_json() == {"type": "stopped", "reason": "instance not active"}
        # The active instance has stopped, so a fresh one may take over.
        with TestClient(create_app(guarded)) as successor:
            assert successor.get("/ready").status_code == 200
    finally:
        active_app.state.engine.dispose()
        standby_app.state.engine.dispose()


def test_a_restart_marks_running_recordings_as_interrupted(
    client: TestClient, org_a: H, db: Session, settings: Settings
) -> None:
    visit = recording_ready(client, org_a)
    session = start_session(client, visit)
    assert session["interaction"]["status"] == "ACTIVE"

    restarted = create_app(settings)
    with TestClient(restarted):  # start-up runs here
        pass
    restarted.state.engine.dispose()

    db.expire_all()
    ia = db.get(ClinicalInteraction, uuid.UUID(session["interaction"]["id"]))
    assert ia is not None and (ia.status, ia.pause_reason) == ("PAUSED", "SERVER_RESTART")
    # Nothing resumes by itself: the audio socket refuses a recording that is not active.
    with client.websocket_connect(session["gateway_path"]) as ws:
        ws.send_json({"type": "auth", "token": token_of(visit.doctor)})
        assert ws.receive_json()["type"] == "stopped"


# --- audio socket origin -------------------------------------------------------------------


def test_the_audio_socket_refuses_a_browser_page_from_another_site(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"cors_origins": ["https://clinic.example"]}))
    path = f"/api/v1/interactions/{uuid.uuid4()}/audio"
    try:
        with TestClient(app) as c:
            with c.websocket_connect(path, headers={"origin": "https://evil.example"}) as ws:
                assert ws.receive_json() == {"type": "stopped", "reason": "origin not allowed"}
            # The clinic's own page and a native app (no Origin header) get as far as authentication.
            for headers in ({"origin": "https://clinic.example"}, {}):
                with c.websocket_connect(path, headers=headers) as ws:
                    ws.send_json({"type": "auth", "token": "not-a-token"})
                    assert ws.receive_json()["reason"] == "invalid token"
    finally:
        app.state.engine.dispose()


# --- usage allowances ----------------------------------------------------------------------


def set_limits(client: TestClient, admin: H, **limits: Any) -> None:
    current = get(client, admin, "/organisations/current/policy").json()
    r = put(client, admin, "/organisations/current/policy", {**current, **limits})
    assert r.status_code == 200, r.text


def test_reaching_the_speech_allowance_stops_new_recordings_but_not_the_visit(
    client: TestClient, org_a: H, db: Session
) -> None:
    visit = recording_ready(client, org_a)
    first = start_session(client, visit)
    post(client, visit.doctor, f"/interactions/{first['interaction']['id']}/stop")
    usage = get(client, org_a, "/usage/limits").json()
    assert usage["speech_minutes"] == {"used": 0.0, "limit": None, "state": "UNLIMITED"}

    set_limits(client, org_a, monthly_speech_minutes_limit=10)
    db.add(
        SpeechUsage(
            organisation_id=db.scalar(
                text("select id from organisations where slug = 'alpha-clinic'")
            ),
            interaction_id=uuid.UUID(first["interaction"]["id"]),
            patient_id=uuid.UUID(visit.patient["id"]),
            user_id=uuid.uuid4(),
            provider="development",
            model="dev",
            audio_seconds=9 * 60,
        )
    )
    db.commit()
    assert get(client, org_a, "/usage/limits").json()["speech_minutes"]["state"] == "NEAR"
    assert create_session(client, visit).status_code == 201  # under the allowance: still allowed

    db.execute(text("update speech_usage set audio_seconds = 600"))
    db.commit()
    assert get(client, org_a, "/usage/limits").json()["speech_minutes"]["state"] == "REACHED"
    refused = create_session(client, visit)
    assert refused.status_code == 409 and refused.json()["title"] == "usage_limit_reached"
    assert "by hand" in refused.json()["detail"]

    # The visit itself carries on without speech: a note can still be written and the visit closed.
    note = post(
        client,
        visit.doctor,
        f"/encounters/{visit.enc_id}/notes",
        {"note_type": "PLAN", "content": "Review in a week."},
    )
    assert note.status_code == 201, note.text


def test_reaching_the_ai_allowance_stops_model_calls_and_says_why(
    client: TestClient, org_a: H, db: Session
) -> None:
    visit = ai_visit(client, org_a)
    iid = ai_interaction(client, visit)
    say(db, iid, [("PATIENT", "I have had a headache for three days.")])
    set_limits(client, org_a, monthly_ai_calls_limit=1)
    assert (
        analyse(client, visit.doctor, iid).status_code == 200
    )  # the first call is within the allowance
    used = db.scalar(text("select count(*) from ai_usage"))
    assert used and used >= 1
    assert get(client, org_a, "/usage/limits").json()["ai_calls"]["state"] == "REACHED"

    refused = analyse(client, visit.doctor, iid)
    assert refused.status_code == 409 and refused.json()["title"] == "usage_limit_reached"
    assert db.scalar(text("select count(*) from ai_usage")) == used  # no call was made

    # Asking about the chart falls back to plain matching and explains itself, without a model call.
    asked = post(
        client,
        visit.doctor,
        f"/patients/{visit.patient['id']}/ai/ask",
        {"question": "any allergies?"},
    )
    assert asked.status_code == 200, asked.text
    assert asked.json()["used_ai"] is False
    assert db.scalar(text("select count(*) from ai_usage")) == used


def test_only_people_with_usage_rights_see_the_allowances_and_bad_limits_are_refused(
    client: TestClient, org_a: H
) -> None:
    visit = recording_ready(client, org_a)
    assert get(client, visit.recep, "/usage/limits").status_code == 403
    assert get(client, visit.doctor, "/usage/limits").status_code == 403
    assert get(client, org_a, "/usage/limits").json()["alert_percent"] == 80
    current = get(client, org_a, "/organisations/current/policy").json()
    bad = put(
        client, org_a, "/organisations/current/policy", {**current, "monthly_ai_calls_limit": -1}
    )
    assert bad.status_code == 422
