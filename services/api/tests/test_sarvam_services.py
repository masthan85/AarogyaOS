"""Sarvam translation, text-to-speech and chat through our interfaces, against a local HTTP server
that speaks the SDK's wire format. The real service is not called."""

import base64
import io
import json
import threading
import wave
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.knowledge import NotAvailable
from app.ai.llm import LLMError, LLMRequest
from app.ai.sarvam import (
    SarvamLLMProvider,
    SarvamTranslationProvider,
    SarvamTTSProvider,
    join_wav,
    numbers_in,
    split_text,
)
from app.modules.summaries import router as summary_router
from tests.ai_helpers import ai_visit
from tests.clinical_helpers import Visit, get, make_visit, post
from tests.test_ai_suggestions import put_json

pytestmark = pytest.mark.anyio
KEY = "sk_test_key_do_not_log"
H = dict[str, str]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def wav(seconds: float = 0.1, rate: int = 22050) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


class Server:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.reply: Callable[[str, dict[str, Any]], tuple[int, dict[str, Any]]] = lambda p, b: (
            200,
            {},
        )
        self.url = ""


@pytest.fixture
def sarvam() -> Iterator[Server]:
    state = Server()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            state.calls.append(
                {
                    "path": self.path,
                    "key": self.headers.get("api-subscription-key"),
                    "body": body,
                }
            )
            status, payload = state.reply(self.path, body)
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    state.url = f"http://127.0.0.1:{server.server_port}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield state
    server.shutdown()


# ---- text splitting and numbers (no network) ---------------------------------------------------


def test_splitting_respects_the_limit_and_never_cuts_a_word() -> None:
    words = ("tablet " * 400).strip()
    parts = split_text(f"First line.\n{words}", 100)
    assert parts[0] == "First line." and all(len(p) <= 100 for p in parts)
    assert " ".join(parts[1:]).split() == words.split()  # nothing lost, nothing cut


def test_a_sentence_longer_than_the_limit_is_still_split_on_spaces() -> None:
    parts = split_text("word " * 100, 40)
    assert all(len(p) <= 40 for p in parts) and " ".join(parts).split() == ["word"] * 100


def test_numbers_are_compared_as_text_so_a_changed_dose_is_caught() -> None:
    assert numbers_in("Take 2 tablets, 500 mg, for 5 days (10,000 units, 0.5 ml)") == sorted(
        ["2", "500", "5", "10,000", "0.5"]
    )


# ---- translation ---------------------------------------------------------------------------------


async def test_translation_sends_the_documented_request(sarvam: Server) -> None:
    sarvam.reply = lambda p, b: (200, {"translated_text": "नमस्ते", "source_language_code": "en-IN"})
    out = await SarvamTranslationProvider(KEY, base_url=sarvam.url).translate(
        "Hello", "en-IN", "hi-IN"
    )
    call = sarvam.calls[0]
    assert out == "नमस्ते" and call["path"] == "/translate" and call["key"] == KEY
    assert call["body"] == {
        "input": "Hello",
        "source_language_code": "en-IN",
        "target_language_code": "hi-IN",
        "model": "sarvam-translate:v1",
        "mode": "formal",
        "numerals_format": "international",
    }


async def test_long_text_is_translated_in_pieces_and_rejoined(sarvam: Server) -> None:
    sarvam.reply = lambda p, b: (
        200,
        {"translated_text": b["input"].upper(), "source_language_code": "en-IN"},
    )
    long = "\n".join(f"Line {i}: take 2 tablets." for i in range(200))
    out = await SarvamTranslationProvider(KEY, base_url=sarvam.url).translate(
        long, "en-IN", "ta-IN"
    )
    assert len(sarvam.calls) > 1 and all(len(c["body"]["input"]) <= 1800 for c in sarvam.calls)
    assert out == long.upper()


async def test_unsupported_languages_and_vendor_failures_are_not_available_without_leaks(
    sarvam: Server,
) -> None:
    p = SarvamTranslationProvider(KEY, base_url=sarvam.url)
    with pytest.raises(NotAvailable):
        await p.translate("Hello", "en-IN", "fr-FR")
    sarvam.reply = lambda path, b: (
        401,
        {"error": {"message": f"bad key {KEY} for patient chest pain"}},
    )
    with pytest.raises(NotAvailable) as exc:
        await p.translate("Hello", "en-IN", "hi-IN")
    assert (
        "401" in str(exc.value) and KEY not in str(exc.value) and "chest pain" not in str(exc.value)
    )


# ---- text to speech --------------------------------------------------------------------------------


async def test_speech_request_and_chunks_are_joined_into_one_wav(sarvam: Server) -> None:
    sarvam.reply = lambda p, b: (200, {"audios": [base64.b64encode(wav(0.1)).decode()]})
    out = await SarvamTTSProvider(KEY, base_url=sarvam.url).synthesize(
        "\n".join(["A sentence to read aloud."] * 200), "hi-IN"
    )
    assert len(sarvam.calls) > 1 and sarvam.calls[0]["path"] == "/text-to-speech"
    assert (
        sarvam.calls[0]["body"]["model"] == "bulbul:v3"
        and sarvam.calls[0]["body"]["output_audio_codec"] == "wav"
    )
    with wave.open(io.BytesIO(out)) as w:
        assert w.getnframes() == int(22050 * 0.1) * len(sarvam.calls)


async def test_speech_refuses_unsupported_languages_and_empty_audio(sarvam: Server) -> None:
    p = SarvamTTSProvider(KEY, base_url=sarvam.url)
    with pytest.raises(NotAvailable):
        await p.synthesize("نمستے", "ur-IN")  # text-to-speech does not cover Urdu
    sarvam.reply = lambda path, b: (200, {"audios": []})
    with pytest.raises(NotAvailable):
        await p.synthesize("Hello", "hi-IN")


def test_mixed_audio_formats_are_not_joined() -> None:
    with pytest.raises(NotAvailable):
        join_wav([wav(rate=22050), wav(rate=16000)])


# ---- chat ------------------------------------------------------------------------------------------


def chat_reply(
    content: str | None, finish: str = "stop", refusal: str | None = None
) -> dict[str, Any]:
    return {
        "id": "c1",
        "object": "chat.completion",
        "created": 1,
        "model": "sarvam-105b",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "message": {"role": "assistant", "content": content, "refusal": refusal},
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


def llm_request() -> LLMRequest:
    return LLMRequest("clinical_extraction", "v1", "SYSTEM", "PROMPT", max_tokens=1500)


async def test_chat_sends_system_and_user_messages_and_returns_real_token_counts(
    sarvam: Server,
) -> None:
    sarvam.reply = lambda p, b: (200, chat_reply('{"candidates": []}'))
    out = await SarvamLLMProvider(KEY, base_url=sarvam.url).complete(llm_request())
    body = sarvam.calls[0]["body"]
    assert sarvam.calls[0]["path"] == "/v1/chat/completions" and sarvam.calls[0]["key"] == KEY
    assert body["model"] == "sarvam-105b" and body["max_tokens"] >= 4000
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert out.text == '{"candidates": []}' and (out.input_tokens, out.output_tokens) == (11, 7)
    assert out.token_counts_are_estimates is False


@pytest.mark.parametrize(
    "reply",
    [
        chat_reply('{"a":', "length"),
        chat_reply(None),
        chat_reply("  "),
        chat_reply("x", refusal="no"),
    ],
)
async def test_cut_off_empty_or_refused_answers_are_errors(
    sarvam: Server, reply: dict[str, Any]
) -> None:
    sarvam.reply = lambda p, b: (200, reply)
    with pytest.raises(LLMError):
        await SarvamLLMProvider(KEY, base_url=sarvam.url).complete(llm_request())


async def test_chat_failures_hide_vendor_text_and_the_key(sarvam: Server) -> None:
    sarvam.reply = lambda p, b: (403, {"error": {"message": f"{KEY} chest pain"}})
    with pytest.raises(LLMError) as exc:
        await SarvamLLMProvider(KEY, base_url=sarvam.url).complete(llm_request())
    assert (
        "403" in str(exc.value) and KEY not in str(exc.value) and "chest pain" not in str(exc.value)
    )
    assert KEY not in repr(SarvamLLMProvider(KEY)) and KEY not in str(SarvamLLMProvider(KEY))
    with pytest.raises(ValueError):
        SarvamLLMProvider("")


# ---- patient summaries: translation and reading aloud --------------------------------------------


class FakeTranslator:
    available = True

    def __init__(self, change_numbers: bool = False) -> None:
        self.change = change_numbers
        self.calls = 0

    async def translate(self, text: str, source: str, target: str) -> str:
        self.calls += 1
        out = f"[{target}] {text}"
        return out.replace("5", "6") if self.change else out


class FakeTTS:
    def __init__(self) -> None:
        self.spoken: list[tuple[str, str]] = []

    async def synthesize(self, text: str, language: str) -> bytes:
        self.spoken.append((text, language))
        return wav()


@pytest.fixture
def v(client: TestClient, org_a: H) -> Visit:
    return ai_visit(client, org_a)


def summary(client: TestClient, v: Visit, **kw: Any) -> Any:
    return post(
        client,
        v.doctor,
        f"/encounters/{v.enc_id}/summaries",
        {"instructions": "Rest for 5 days.", **kw},
    )


def test_a_translated_summary_is_a_draft_marked_as_machine_made(
    client: TestClient, v: Visit, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeTranslator()
    monkeypatch.setattr(summary_router, "get_translator", lambda s: fake)
    s = summary(client, v, language="hi-IN").json()
    assert s["translation_status"] == "MACHINE_DRAFT" and s["language"] == "hi-IN"
    assert s["content"].startswith("[hi-IN] ") and "Rest for 5 days." in s["source_content"]
    assert s["status"] == "DRAFT"  # a doctor still has to read and approve it


def test_a_translation_that_changes_a_number_is_flagged_for_the_doctor(
    client: TestClient, v: Visit, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        summary_router, "get_translator", lambda s: FakeTranslator(change_numbers=True)
    )
    s = summary(client, v, language="hi-IN").json()
    assert s["translation_status"] == "NUMBERS_MISMATCH"
    edited = put_json(
        client, v.doctor, f"/summaries/{s['id']}", {"content": "Corrected by the doctor."}
    )
    assert edited.json()["translation_status"] == "CLINICIAN_EDITED"


def test_nothing_is_sent_for_translation_without_the_organisations_switch_and_consent(
    client: TestClient, org_a: H, monkeypatch: pytest.MonkeyPatch
) -> None:
    visit = make_visit(client, org_a, stage="consult")  # no AI switch, no AI consent
    fake = FakeTranslator()
    monkeypatch.setattr(summary_router, "get_translator", lambda s: fake)
    s = summary(client, visit, language="hi-IN").json()
    assert (
        s["translation_status"] == "NOT_CONSENTED" and s["language"] == "en-IN" and fake.calls == 0
    )


def test_english_needs_no_translation_and_no_vendor_call(
    client: TestClient, v: Visit, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeTranslator()
    monkeypatch.setattr(summary_router, "get_translator", lambda s: fake)
    assert summary(client, v, language="en-IN").json()["translation_status"] == "NOT_NEEDED"
    assert fake.calls == 0


def approved(client: TestClient, v: Visit) -> dict[str, Any]:
    s = summary(client, v).json()
    out = post(client, v.doctor, f"/summaries/{s['id']}/approve")
    assert out.status_code == 200, out.text
    return dict(out.json())


def test_an_approved_summary_can_be_read_aloud_without_storing_the_audio(
    client: TestClient, v: Visit, monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    tts = FakeTTS()
    monkeypatch.setattr(summary_router, "get_tts", lambda s: tts)
    s = approved(client, v)
    r = post(client, v.doctor, f"/summaries/{s['id']}/speech")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert r.headers["cache-control"] == "no-store" and r.content[:4] == b"RIFF"
    assert tts.spoken == [(s["content"], "en-IN")]  # the approved words, exactly
    assert db.execute(text("select feature, status from ai_usage")).all() == [("speech", "OK")]
    assert (
        db.execute(
            text("select count(*) from audit_logs where action = 'PATIENT_SUMMARY_SPOKEN'")
        ).scalar()
        == 1
    )


def test_only_approved_text_is_ever_spoken(
    client: TestClient, v: Visit, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(summary_router, "get_tts", lambda s: FakeTTS())
    draft = summary(client, v).json()
    assert post(client, v.doctor, f"/summaries/{draft['id']}/speech").status_code == 409


def test_reading_aloud_needs_consent_a_connected_service_and_the_right_role(
    client: TestClient, v: Visit, org_a: H, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = approved(client, v)
    url = f"/summaries/{s['id']}/speech"
    assert post(client, v.doctor, url).status_code == 503  # no text-to-speech service connected
    monkeypatch.setattr(summary_router, "get_tts", lambda s: FakeTTS())
    for h in (v.nurse, v.recep):
        assert post(client, h, url).status_code == 403
    off = put_json(
        client,
        org_a,
        "/organisations/current/policy",
        {"recording_enabled": True, "ai_processing_enabled": False},
    )
    assert off.status_code == 200
    assert post(client, v.doctor, url).status_code == 409  # organisation switch off


def test_reading_aloud_is_rate_limited(
    client: TestClient, v: Visit, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(summary_router, "get_tts", lambda s: FakeTTS())
    s = approved(client, v)
    client.app.state.settings.ai_analyses_per_minute = 2  # type: ignore[attr-defined]
    try:
        codes = [
            post(client, v.doctor, f"/summaries/{s['id']}/speech").status_code for _ in range(3)
        ]
    finally:
        client.app.state.settings.ai_analyses_per_minute = 6  # type: ignore[attr-defined]
    assert codes == [200, 200, 429]


def test_vendor_failure_returns_503_and_is_recorded(
    client: TestClient, v: Visit, monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    class Broken:
        async def synthesize(self, text: str, language: str) -> bytes:
            raise NotAvailable("Sarvam text-to-speech failed (status 500)")

    monkeypatch.setattr(summary_router, "get_tts", lambda s: Broken())
    s = approved(client, v)
    r = post(client, v.doctor, f"/summaries/{s['id']}/speech")
    assert r.status_code == 503
    assert db.execute(text("select feature, status from ai_usage")).all() == [("speech", "ERROR")]
    assert get(client, v.doctor, f"/encounters/{v.enc_id}/summaries").status_code == 200


def test_services_are_off_unless_explicitly_chosen() -> None:
    from app.ai.services import get_translator, get_tts
    from app.core.config import Settings

    keyed = Settings(sarvam_api_key=KEY)  # type: ignore[arg-type]  # a key alone enables nothing
    assert get_translator(keyed).available is False
    with pytest.raises(NotAvailable):
        get_tts(keyed)
    on = Settings(sarvam_api_key=KEY, translation_provider="sarvam", tts_provider="sarvam")  # type: ignore[arg-type]
    assert get_translator(on).available is True and get_tts(on).supports("hi-IN")
