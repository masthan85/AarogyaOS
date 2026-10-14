"""The Anthropic adapter against a stub client (the real API is not called in tests)."""

import json
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2 as httpx
import pytest

from app.ai import guardrails
from app.ai.anthropic_llm import MIN_MAX_TOKENS, AnthropicLLMProvider
from app.ai.llm import LLMError, LLMRequest
from app.ai.registry import get_llm
from app.ai.schemas import ExtractionEnvelope

pytestmark = pytest.mark.anyio
KEY = "sk-ant-secret-key-do-not-log"
REQ = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def message(text: str = "{}", stop: str = "end_turn", blocks: list[Any] | None = None) -> Any:
    content = blocks if blocks is not None else [SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(
        content=content,
        stop_reason=stop,
        usage=SimpleNamespace(input_tokens=120, output_tokens=45),
    )


class Stub:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._result, self._error = result, error
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kw: Any) -> Any:
        self.calls.append(kw)
        if self._error:
            raise self._error
        return self._result


def request(**kw: Any) -> LLMRequest:
    return LLMRequest("clinical_extraction", "v1", "SYSTEM", "PROMPT", max_tokens=1500, **kw)


async def test_it_sends_the_prompt_and_returns_text_with_real_token_counts() -> None:
    stub = Stub(message('{"candidates": []}'))
    out = await AnthropicLLMProvider("k", client=stub).complete(request())
    call = stub.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["system"] == "SYSTEM" and call["messages"] == [
        {"role": "user", "content": "PROMPT"}
    ]
    assert out.text == '{"candidates": []}'
    assert (out.input_tokens, out.output_tokens) == (120, 45)
    assert out.token_counts_are_estimates is False


async def test_it_sends_nothing_the_current_models_reject() -> None:
    stub = Stub(message())
    await AnthropicLLMProvider("k", client=stub).complete(request(temperature=0.0))
    call = stub.calls[0]
    for forbidden in ("temperature", "top_p", "top_k", "thinking", "tool_choice", "betas"):
        assert forbidden not in call
    assert call["max_tokens"] == MIN_MAX_TOKENS  # room for thinking plus the answer


async def test_only_text_blocks_are_returned_never_thinking() -> None:
    blocks = [
        SimpleNamespace(type="thinking", thinking="secret reasoning", text="secret reasoning"),
        SimpleNamespace(type="text", text='{"a":'),
        SimpleNamespace(type="text", text="1}"),
    ]
    out = await AnthropicLLMProvider("k", client=Stub(message(blocks=blocks))).complete(request())
    assert out.text == '{"a":1}'


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
async def test_a_refusal_or_truncation_is_an_error_not_a_partial_result(stop: str) -> None:
    with pytest.raises(LLMError):
        await AnthropicLLMProvider("k", client=Stub(message('{"candidates": [', stop))).complete(
            request()
        )


async def test_empty_output_is_an_error() -> None:
    with pytest.raises(LLMError):
        await AnthropicLLMProvider("k", client=Stub(message("   "))).complete(request())


@pytest.mark.parametrize(
    ("error", "fragment"),
    [
        (anthropic.APIConnectionError(request=REQ), "unreachable"),
        (anthropic.APITimeoutError(request=REQ), "timed out"),
        (
            anthropic.RateLimitError(
                f"quota for {KEY} patient has chest pain",
                response=httpx.Response(429, request=REQ),
                body=None,
            ),
            "429",
        ),
    ],
)
async def test_vendor_failures_become_llm_errors_without_content_or_key(
    error: Exception, fragment: str
) -> None:
    with pytest.raises(LLMError) as exc:
        await AnthropicLLMProvider("k", client=Stub(error=error)).complete(request())
    assert fragment in str(exc.value)
    assert KEY not in str(exc.value) and "chest pain" not in str(exc.value)


def test_a_key_is_required_and_never_shown() -> None:
    with pytest.raises(ValueError):
        AnthropicLLMProvider("")
    p = AnthropicLLMProvider(KEY)
    assert KEY not in repr(p) and KEY not in str(p)
    assert p.is_development is False and p.name == "anthropic"


def test_without_a_key_the_registry_says_why_and_the_dev_llm_stays_refused_in_production() -> None:
    with pytest.raises(Exception, match="AAROGYA_ANTHROPIC_API_KEY"):
        get_llm("anthropic", environment="production")


async def test_model_output_still_goes_through_the_same_guardrails() -> None:
    """A confident, ungrounded model answer is dropped; a grounded one survives: the provider is
    not trusted, whichever model sits behind it."""
    segments = [guardrails.SegmentView(1, "I have had fever for three days.", "PATIENT", "seg-1")]
    reply = json.dumps(
        {
            "candidates": [
                {
                    "kind": "SYMPTOM",
                    "text": "fever",
                    "assertion": "PRESENT",
                    "subject": "PATIENT",
                    "attributes": {},
                    "original_term": None,
                    "evidence": [{"seq": 1, "quote": "fever for three days"}],
                },
                {
                    "kind": "SYMPTOM",
                    "text": "chest pain",
                    "assertion": "PRESENT",
                    "subject": "PATIENT",
                    "attributes": {},
                    "original_term": None,
                    "evidence": [{"seq": 1, "quote": "severe chest pain"}],  # never said
                },
            ]
        }
    )
    out = await AnthropicLLMProvider("k", client=Stub(message(reply))).complete(request())
    envelope = ExtractionEnvelope.model_validate(json.loads(out.text))
    vetted = guardrails.vet_candidates(envelope.candidates, segments, "CONSULTATION")
    assert [v.candidate.text for v in vetted.kept] == ["fever"]
    assert vetted.dropped == {"unsupported_evidence": 1}


async def test_the_real_sdk_puts_the_expected_request_on_the_wire() -> None:
    """Same provider, real SDK client, local HTTP server: checks what is actually sent."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen: dict[str, Any] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.update(
                path=self.path, headers={k.lower(): v for k, v in self.headers.items()}, body=body
            )
            reply = json.dumps(
                {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "model": body["model"],
                    "content": [{"type": "text", "text": '{"candidates": []}'}],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 7, "output_tokens": 3},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *a: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = anthropic.AsyncAnthropic(
            api_key=KEY, base_url=f"http://127.0.0.1:{server.server_port}", max_retries=0
        )
        out = await AnthropicLLMProvider("k", client=client).complete(request())
    finally:
        server.shutdown()
    assert out.text == '{"candidates": []}' and (out.input_tokens, out.output_tokens) == (7, 3)
    assert seen["path"] == "/v1/messages"
    assert seen["headers"]["x-api-key"] == KEY and "anthropic-version" in seen["headers"]
    assert set(seen["body"]) == {"model", "max_tokens", "system", "messages"}
