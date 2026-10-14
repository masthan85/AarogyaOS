"""Builders for consent, recording and gateway tests."""

from typing import Any

from fastapi.testclient import TestClient

from tests.clinical_helpers import API, Visit, get, make_visit, post

Headers = dict[str, str]
RECORD = ["AUDIO_RECORDING", "SPEECH_TRANSCRIPTION"]
SECOND = b"\x00\x00" * 16000  # exactly one second of 16 kHz mono PCM16 silence (32,000 bytes)


def put(client: TestClient, h: Headers, url: str, body: dict[str, Any]) -> Any:
    return client.put(f"{API}{url}", headers=h, json=body)


def enable_recording(
    client: TestClient, admin: Headers, *, ai: bool = False, retain_days: int | None = None
) -> None:
    body: dict[str, Any] = {"recording_enabled": True, "ai_processing_enabled": ai}
    if retain_days:
        body.update(audio_retention="RETAIN_DAYS", retain_days=retain_days)
    r = put(client, admin, "/organisations/current/policy", body)
    assert r.status_code == 200, r.text


def install_wording(client: TestClient, admin: Headers) -> None:
    r = post(client, admin, "/consent-policies/install-templates")
    assert r.status_code == 201, r.text


def grant(
    client: TestClient, h: Headers, patient_id: str, *purposes: str, **kw: Any
) -> list[dict[str, Any]]:
    out = []
    for purpose in purposes:
        body = {"purpose": purpose, "method": "VERBAL_WITNESSED", **kw}
        r = post(client, h, f"/patients/{patient_id}/consents", body)
        assert r.status_code == 201, r.text
        out.append(r.json())
    return out


def recording_ready(
    client: TestClient, admin: Headers, *, ai: bool = False, retain_days: int | None = None
) -> Visit:
    """A patient in consultation with recording enabled and the recording consents granted."""
    v = make_visit(client, admin, stage="consult")
    enable_recording(client, admin, ai=ai, retain_days=retain_days)
    install_wording(client, admin)
    purposes = (
        RECORD + (["AI_PROCESSING"] if ai else []) + (["AUDIO_RETENTION"] if retain_days else [])
    )
    grant(client, v.recep, v.patient["id"], *purposes)
    return v


def create_session(client: TestClient, v: Visit, **kw: Any) -> Any:
    body = {
        "patient_id": v.patient["id"],
        "purpose": "CONSULTATION",
        "encounter_id": v.enc_id,
        **kw,
    }
    return post(client, v.doctor, "/interactions", body)


def start_session(client: TestClient, v: Visit, **kw: Any) -> dict[str, Any]:
    r = create_session(client, v, **kw)
    assert r.status_code == 201, r.text
    s = post(client, v.doctor, f"/interactions/{r.json()['id']}/start")
    assert s.status_code == 200, s.text
    return s.json()


def token_of(h: Headers) -> str:
    return h["Authorization"].split()[1]


def stream(ws: Any, seconds: int) -> None:
    for _ in range(seconds):
        ws.send_bytes(SECOND)


def open_gateway(client: TestClient, session: dict[str, Any], h: Headers):  # type: ignore[no-untyped-def]
    """Returns a context manager for an authenticated gateway connection (auth already sent)."""
    return client.websocket_connect(session["gateway_path"])


def transcript(
    client: TestClient, h: Headers, interaction_id: str, after: int = 0
) -> dict[str, Any]:
    r = get(client, h, f"/interactions/{interaction_id}/transcript", after_seq=after)
    assert r.status_code == 200, r.text
    return r.json()
