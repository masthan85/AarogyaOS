"""End-to-end tests of the audio WebSocket: audio in, consented transcript out."""

import logging
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.core.db import set_tenant
from app.modules.interactions import gateway
from app.modules.interactions.retention import purge_due_audio
from app.speech.dev_provider import DevelopmentSpeechProvider
from app.speech.provider import ProviderError, RecognisedSegment, StreamOptions
from app.speech.registry import register
from tests.clinical_helpers import Visit, get, post
from tests.speech_helpers import (
    recording_ready,
    start_session,
    stream,
    token_of,
    transcript,
)

H = dict[str, str]


class FailsAfter(DevelopmentSpeechProvider):
    """Raises (with a message containing text that must never be logged) after N frames."""

    name, model = "flaky", "flaky-1"

    def __init__(self, frames_ok: int) -> None:
        super().__init__()
        self._ok = frames_ok

    async def stream_transcribe(  # type: ignore[override]
        self, audio: AsyncIterator[bytes], opts: StreamOptions
    ) -> AsyncIterator[RecognisedSegment]:
        seen = 0
        async for _ in audio:
            seen += 1
            if seen > self._ok:
                raise ProviderError("vendor said: patient has chest pain")
        return
        yield  # pragma: no cover


@pytest.fixture
def v(client: TestClient, org_a: H) -> Visit:
    return recording_ready(client, org_a)


def connect(client: TestClient, session: dict[str, Any], token: str | None):  # type: ignore[no-untyped-def]
    ws = client.websocket_connect(session["gateway_path"])
    return ws


def authed(ws: Any, token: str) -> dict[str, Any]:
    ws.send_json({"type": "auth", "token": token})
    msg: dict[str, Any] = ws.receive_json()
    return msg


def closes_with(ws: Any) -> int:
    """Read until the server closes; return the close code."""
    while True:
        try:
            ws.receive_json()
        except WebSocketDisconnect as exc:
            return int(exc.code)


def wait_until(check: Any, seconds: float = 5.0) -> None:
    """Poll until `check()` is truthy. The server finishes its cleanup after a client hangs up."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.05)
    raise AssertionError("condition not reached in time")


def interaction(client: TestClient, v: Visit, iid: str) -> dict[str, Any]:
    r = get(client, v.doctor, f"/interactions/{iid}")
    assert r.status_code == 200
    body: dict[str, Any] = r.json()
    return body


# ---- the happy path ----------------------------------------------------------------


def test_audio_in_final_segments_out_with_full_metadata(client: TestClient, v: Visit) -> None:
    session = start_session(client, v, language_hint="te-IN")
    iid = session["interaction"]["id"]
    with connect(client, session, None) as ws:
        ready = authed(ws, token_of(v.doctor))
        assert ready["type"] == "ready" and ready["format"]["sample_rate"] == 16000
        stream(ws, 6)
        ws.send_json({"type": "stop"})
        assert closes_with(ws) == 1000
    t = transcript(client, v.doctor, iid)
    assert t["status"] == "ENDED" and t["is_development"] is True
    assert [s["seq"] for s in t["segments"]] == [1, 2]  # finals only: partials are never stored
    first, mixed = t["segments"]
    assert (
        mixed["raw_text"]
        == "Naku two days nunchi fever undi, night time ekkuva avutundi and little breathing problem."
    )
    assert mixed["language"] == "te-IN" and mixed["secondary_language"] == "en-IN"
    assert [mixed["raw_text"][s["start"] : s["end"]] for s in mixed["code_switch_spans"]] == [
        "two days",
        "night time",
        "little breathing problem",
    ]
    assert mixed["confidence"] == 0.74 and mixed["provider"] == "development"
    assert mixed["normalised_text"] is None  # clinical normalisation is a later, separate layer
    assert first["end_ms"] <= mixed["start_ms"]
    # Nobody has said who the speakers are, so nobody is assumed to be the doctor.
    assert {s["speaker_role"] for s in t["segments"]} == {"UNKNOWN"}
    assert [(s["speaker_id"], s["role"]) for s in t["speakers"]] == [
        ("spk_0", "UNKNOWN"),
        ("spk_1", "UNKNOWN"),
    ]


def test_speaker_roles_assigned_by_a_person_apply_to_the_whole_transcript(
    client: TestClient, v: Visit
) -> None:
    session = start_session(client, v)
    iid = session["interaction"]["id"]
    with connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        stream(ws, 12)
        ws.send_json({"type": "stop"})
        closes_with(ws)
    for speaker, role in (("spk_0", "DOCTOR"), ("spk_1", "PATIENT")):
        r = client.put(
            f"/api/v1/interactions/{iid}/speakers/{speaker}", headers=v.doctor, json={"role": role}
        )
        assert r.status_code == 200
    roles = [
        (s["speaker_id"], s["speaker_role"]) for s in transcript(client, v.doctor, iid)["segments"]
    ]
    assert roles == [
        ("spk_0", "DOCTOR"),
        ("spk_1", "PATIENT"),
        ("spk_0", "DOCTOR"),
        ("spk_1", "PATIENT"),
    ]
    # The recognised text itself is untouched by the correction.
    assert transcript(client, v.doctor, iid)["segments"][3]["raw_text"].startswith(
        "No breathing trouble"
    )


def test_incremental_polling_returns_only_new_segments(client: TestClient, v: Visit) -> None:
    session = start_session(client, v)
    iid = session["interaction"]["id"]
    with connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        stream(ws, 12)
        ws.send_json({"type": "stop"})
        closes_with(ws)
    assert [s["seq"] for s in transcript(client, v.doctor, iid, after=2)["segments"]] == [3, 4]
    assert transcript(client, v.doctor, iid, after=4)["segments"] == []


def test_usage_is_metered_without_content(client: TestClient, v: Visit) -> None:
    session = start_session(client, v)
    with connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        stream(ws, 12)
        ws.send_json({"type": "stop"})
        closes_with(ws)
    row = get(client, v.admin, "/usage/speech").json()[0]
    assert row["provider"] == "development" and row["sessions"] == 1
    assert row["audio_seconds"] == 12 and row["segments"] == 4 and row["errors"] == 0
    assert row["avg_first_segment_latency_ms"] is not None
    assert row["estimated_cost_paise"] is None  # no price is known, so none is invented
    assert get(client, v.doctor, "/usage/speech").status_code == 403


def test_server_sent_events_replay_a_finished_transcript(client: TestClient, v: Visit) -> None:
    session = start_session(client, v)
    iid = session["interaction"]["id"]
    with connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        stream(ws, 6)
        ws.send_json({"type": "stop"})
        closes_with(ws)
    with client.stream("GET", f"/api/v1/interactions/{iid}/events", headers=v.doctor) as r:
        body = "".join(r.iter_text())
    assert body.count("event: segment") == 2 and "event: end" in body
    assert client.get(f"/api/v1/interactions/{iid}/events").status_code == 401
    assert len(get(client, v.admin, "/audit-logs", action="TRANSCRIPT_VIEWED").json()) == 1


# ---- authentication and authorisation ----------------------------------------------


@pytest.mark.parametrize(
    "first", [{"type": "hello"}, {"type": "auth"}, {"type": "auth", "token": 5}]
)
def test_the_first_message_must_be_a_valid_auth_message(
    client: TestClient, v: Visit, first: dict[str, Any]
) -> None:
    session = start_session(client, v)
    with connect(client, session, None) as ws:
        ws.send_json(first)
        assert closes_with(ws) == 4401


def test_bad_and_foreign_tokens_are_refused(client: TestClient, v: Visit, org_b: H) -> None:
    session = start_session(client, v)
    with connect(client, session, None) as ws:
        ws.send_json({"type": "auth", "token": "junk"})
        assert closes_with(ws) == 4401
    for outsider in (v.nurse, v.recep):
        with connect(client, session, None) as ws:
            ws.send_json({"type": "auth", "token": token_of(outsider)})
            assert closes_with(ws) == 4404  # not a participant: existence is not revealed
    from tests.conftest import make_staff

    doc_b, _ = make_staff(client, org_b, "dr@beta.example.com", "doctor", "beta-hospital")
    with connect(client, session, None) as ws:
        ws.send_json({"type": "auth", "token": token_of(doc_b)})
        assert closes_with(ws) == 4404


def test_a_silent_client_is_dropped(
    client: TestClient, v: Visit, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gateway, "AUTH_TIMEOUT_SECONDS", 0.2)
    session = start_session(client, v)
    with connect(client, session, None) as ws:
        assert closes_with(ws) == 4401


def test_only_an_active_session_accepts_audio(client: TestClient, v: Visit) -> None:
    created = post(
        client,
        v.doctor,
        "/interactions",
        {"patient_id": v.patient["id"], "purpose": "CONSULTATION", "encounter_id": v.enc_id},
    ).json()
    path = f"/api/v1/interactions/{created['id']}/audio"
    with client.websocket_connect(path) as ws:
        ws.send_json({"type": "auth", "token": token_of(v.doctor)})
        assert closes_with(ws) == 4409  # created but never started: nothing may record
    post(client, v.doctor, f"/interactions/{created['id']}/start")
    post(client, v.doctor, f"/interactions/{created['id']}/stop")
    with client.websocket_connect(path) as ws:
        ws.send_json({"type": "auth", "token": token_of(v.doctor)})
        assert closes_with(ws) == 4409


def test_the_gateway_checks_consent_itself_even_if_the_session_looks_active(
    client: TestClient, v: Visit, db: Session
) -> None:
    session = start_session(client, v)
    history = get(client, v.recep, f"/patients/{v.patient['id']}/consents").json()["history"]
    consent = next(c for c in history if c["purpose"] == "AUDIO_RECORDING")
    post(client, v.recep, f"/consents/{consent['id']}/withdraw", {})
    db.execute(text("update clinical_interactions set status = 'ACTIVE', ended_at = null"))
    db.commit()  # simulate a stale row: the session claims to be active
    with connect(client, session, None) as ws:
        ws.send_json({"type": "auth", "token": token_of(v.doctor)})
        assert closes_with(ws) == 4403


def test_recording_switched_off_by_the_organisation_stops_new_streams(
    client: TestClient, v: Visit
) -> None:
    session = start_session(client, v)
    client.put(
        "/api/v1/organisations/current/policy", headers=v.admin, json={"recording_enabled": False}
    )
    with connect(client, session, None) as ws:
        ws.send_json({"type": "auth", "token": token_of(v.doctor)})
        assert closes_with(ws) == 4403


def test_an_unbuilt_provider_closes_with_a_service_code(client: TestClient, v: Visit) -> None:
    session = start_session(client, v)
    client.app.state.settings.speech_provider = "sarvam"  # type: ignore[attr-defined]
    with connect(client, session, None) as ws:
        ws.send_json({"type": "auth", "token": token_of(v.doctor)})
        assert closes_with(ws) == 4503


def test_only_one_connection_per_session(client: TestClient, v: Visit) -> None:
    session = start_session(client, v)
    with connect(client, session, None) as first:
        authed(first, token_of(v.doctor))
        with connect(client, session, None) as second:
            second.send_json({"type": "auth", "token": token_of(v.doctor)})
            assert closes_with(second) == 4409
        first.send_json({"type": "stop"})
        closes_with(first)


# ---- keeping the recording state honest ---------------------------------------------


def test_withdrawing_consent_mid_stream_stops_the_audio(client: TestClient, v: Visit) -> None:
    session = start_session(client, v)
    iid = session["interaction"]["id"]
    history = get(client, v.recep, f"/patients/{v.patient['id']}/consents").json()["history"]
    consent = next(c for c in history if c["purpose"] == "SPEECH_TRANSCRIPTION")
    with connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        stream(ws, 1)
        assert post(client, v.recep, f"/consents/{consent['id']}/withdraw", {}).status_code == 200
        assert closes_with(ws) == 4001
    assert interaction(client, v, iid)["end_reason"] == "CONSENT_WITHDRAWN"


def test_a_dropped_connection_pauses_the_session_and_resuming_continues_the_transcript(
    client: TestClient, v: Visit
) -> None:
    session = start_session(client, v)
    iid = session["interaction"]["id"]
    with connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        stream(ws, 4)
        ws.close(1001)  # no stop message: the phone just loses signal
        wait_until(lambda: interaction(client, v, iid)["status"] == "PAUSED")
    ia = interaction(client, v, iid)
    assert (
        ia["status"] == "PAUSED" and ia["pause_reason"] == "CONNECTION_LOST"
    )  # never says 'recording' falsely
    before = transcript(client, v.doctor, iid)["segments"]
    assert post(client, v.doctor, f"/interactions/{iid}/resume").json()["status"] == "ACTIVE"
    with connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        stream(ws, 4)
        ws.send_json({"type": "stop"})
        closes_with(ws)
    after = transcript(client, v.doctor, iid)["segments"]
    assert [s["seq"] for s in after] == list(range(1, len(after) + 1))  # numbering continues
    assert after[len(before)]["start_ms"] >= before[-1]["end_ms"]  # time keeps moving forward


def test_time_limit_pauses_the_session(client: TestClient, v: Visit) -> None:
    client.app.state.settings.speech_max_session_seconds = 2  # type: ignore[attr-defined]
    session = start_session(client, v)
    iid = session["interaction"]["id"]
    with connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        stream(ws, 4)
        assert closes_with(ws) == 4002
    ia = interaction(client, v, iid)
    assert ia["status"] == "PAUSED" and ia["pause_reason"] == "MAX_DURATION"


@pytest.mark.parametrize("frame", [b"\x00\x00\x00", b"\x00" * 70000])
def test_malformed_audio_frames_are_refused(client: TestClient, v: Visit, frame: bytes) -> None:
    session = start_session(client, v)
    iid = session["interaction"]["id"]
    with connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        ws.send_bytes(frame)
        assert closes_with(ws) == 4001
    assert interaction(client, v, iid)["pause_reason"] == "BAD_FRAME"


# ---- provider failure and fallback -------------------------------------------------


def test_provider_failure_pauses_cleanly_and_leaks_nothing(
    client: TestClient, v: Visit, caplog: pytest.LogCaptureFixture
) -> None:
    register("flaky", lambda: FailsAfter(0))
    client.app.state.settings.speech_provider = "flaky"  # type: ignore[attr-defined]
    session = start_session(client, v)
    iid = session["interaction"]["id"]
    with caplog.at_level(logging.DEBUG), connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        stream(ws, 2)
        assert closes_with(ws) == 1011
    ia = interaction(client, v, iid)
    assert ia["status"] == "PAUSED" and ia["pause_reason"] == "PROVIDER_ERROR"
    assert "chest pain" not in caplog.text  # vendor error text is never logged
    assert get(client, v.admin, "/usage/speech").json()[0]["errors"] == 1


def test_fallback_provider_takes_over_and_the_gap_is_recorded(client: TestClient, v: Visit) -> None:
    register("flaky", lambda: FailsAfter(1))
    settings = client.app.state.settings  # type: ignore[attr-defined]
    settings.speech_provider, settings.speech_fallback_provider = "flaky", "development"
    session = start_session(client, v)
    iid = session["interaction"]["id"]
    with connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        stream(ws, 10)
        ws.send_json({"type": "stop"})
        closes_with(ws)
    t = transcript(client, v.doctor, iid)
    assert t["segments"] and {s["provider"] for s in t["segments"]} == {"development"}
    row = get(client, v.admin, "/usage/speech").json()[0]
    assert row["fallbacks"] == 1 and row["errors"] == 1 and row["provider"] == "development"


# ---- privacy ----------------------------------------------------------------------


def test_nothing_is_logged_or_audited_from_the_conversation(
    client: TestClient, v: Visit, caplog: pytest.LogCaptureFixture
) -> None:
    session = start_session(client, v, language_hint="te-IN")
    with caplog.at_level(logging.DEBUG), connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        stream(ws, 6)
        ws.send_json({"type": "stop"})
        closes_with(ws)
    blobs = [caplog.text.lower(), get(client, v.admin, "/audit-logs", limit=200).text.lower()]
    events = get(client, v.doctor, f"/patients/{v.patient['id']}/timeline").text.lower()
    for blob in (*blobs, events):
        assert "breathing" not in blob and "nunchi" not in blob


def test_transcript_segments_cannot_be_edited_or_deleted_even_with_sql(
    client: TestClient, v: Visit
) -> None:
    session = start_session(client, v)
    with connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        stream(ws, 3)
        ws.send_json({"type": "stop"})
        closes_with(ws)
    maker = client.app.state.sessionmaker  # type: ignore[attr-defined]
    for sql in (
        "update transcript_segments set raw_text = 'tampered'",
        "update transcript_segments set normalised_text = 'x'",
        "delete from transcript_segments",
    ):
        with maker() as s:
            set_tenant(s, None, bypass=True)
            with pytest.raises(DBAPIError):
                s.execute(text(sql))
                s.commit()


# ---- audio retention --------------------------------------------------------------


def audio_rows(db: Session) -> list[Any]:
    return list(
        db.execute(
            text("select storage_key, bytes, retain_until, deleted_at from audio_assets")
        ).all()
    )


def test_by_default_audio_is_never_stored(
    client: TestClient, v: Visit, db: Session, tmp_path: Any
) -> None:
    session = start_session(client, v)
    assert session["interaction"]["retain_audio"] is False
    with connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        stream(ws, 4)
        ws.send_json({"type": "stop"})
        closes_with(ws)
    assert audio_rows(db) == []
    assert not (tmp_path / "audio").exists() or not any((tmp_path / "audio").rglob("*.audio"))


def test_org_policy_alone_does_not_retain_audio_without_the_patients_consent(
    client: TestClient, org_a: H, db: Session
) -> None:
    v = make = recording_ready(client, org_a)  # consents: recording + transcription only
    assert make
    client.put(
        "/api/v1/organisations/current/policy",
        headers=org_a,
        json={"recording_enabled": True, "audio_retention": "RETAIN_DAYS", "retain_days": 7},
    )
    session = start_session(client, v)
    assert session["interaction"]["retain_audio"] is False
    post(client, v.doctor, f"/interactions/{session['interaction']['id']}/stop")
    assert audio_rows(db) == []


def test_retained_audio_is_encrypted_expires_and_is_purged(
    client: TestClient, org_a: H, db: Session, tmp_path: Any
) -> None:
    v = recording_ready(client, org_a, retain_days=7)
    session = start_session(client, v)
    iid = session["interaction"]["id"]
    assert session["interaction"]["retain_audio"] is True
    sent = bytes([1, 2, 3, 4]) * 8000  # a recognisable, non-silent second
    with connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        for _ in range(3):
            ws.send_bytes(sent)
        ws.send_json({"type": "stop"})
        closes_with(ws)
    (key, size, until, deleted) = audio_rows(db)[0]
    assert size == 3 * len(sent) and deleted is None
    assert abs((until - datetime.now(UTC)) - timedelta(days=7)) < timedelta(minutes=5)
    store = client.app.state.audio_store  # type: ignore[attr-defined]
    on_disk = (tmp_path / "audio" / key).read_bytes()
    assert sent[:64] not in on_disk  # encrypted at rest
    assert b"".join(store.read_chunks(key)) == sent * 3  # and recoverable with the key
    assert purge_due_audio(db, store, datetime.now(UTC)) == 0  # not due yet
    removed = purge_due_audio(db, store, datetime.now(UTC) + timedelta(days=8))
    assert removed == 1 and not store.exists(key)
    (key2, _, _, deleted2) = audio_rows(db)[0]
    assert key2 is None and deleted2 is not None
    audit = get(client, v.admin, "/audit-logs", action="AUDIO_PURGED").json()
    assert audit and audit[0]["reason"] == "RETENTION_EXPIRED"
    assert transcript(client, v.doctor, iid)["status"] == "ENDED"  # the transcript is not touched


def test_withdrawing_retention_consent_queues_the_audio_for_deletion(
    client: TestClient, org_a: H, db: Session
) -> None:
    v = recording_ready(client, org_a, retain_days=30)
    session = start_session(client, v)
    with connect(client, session, None) as ws:
        authed(ws, token_of(v.doctor))
        stream(ws, 2)
        ws.send_json({"type": "stop"})
        closes_with(ws)
    store = client.app.state.audio_store  # type: ignore[attr-defined]
    key = audio_rows(db)[0][0]
    assert store.exists(key)
    history = get(client, v.recep, f"/patients/{v.patient['id']}/consents").json()["history"]
    retention = next(c for c in history if c["purpose"] == "AUDIO_RETENTION")
    post(client, v.recep, f"/consents/{retention['id']}/withdraw", {"reason": "Please delete it"})
    assert purge_due_audio(db, store) == 1 and not store.exists(key)
    assert (
        get(client, v.admin, "/audit-logs", action="AUDIO_PURGED").json()[0]["reason"]
        == "CONSENT_WITHDRAWN"
    )
