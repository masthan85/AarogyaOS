import json

import httpx
import pytest

from app.ai.llm import LLMError, LLMRequest
from app.ai.registry import get_llm, register, unregister
from app.ai.self_hosted import SelfHostedLLMProvider, address_problem
from app.core.config import Settings

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


SECRET = "patient says she has chest tightness"


def request() -> LLMRequest:
    return LLMRequest("clinical_extraction", "v1", "SYSTEM", f"PROMPT {SECRET}", max_tokens=500)


def provider(handler: httpx.MockTransport | None = None, **kw: object) -> SelfHostedLLMProvider:
    return SelfHostedLLMProvider(
        "http://127.0.0.1:8000/v1",
        model="qwen",
        transport=handler,
        **kw,  # type: ignore[arg-type]
    )


def ok(
    content: str = '{"candidates": []}', finish: str = "stop", usage: bool = True
) -> httpx.Response:
    body: dict[str, object] = {
        "choices": [{"message": {"content": content}, "finish_reason": finish}]
    }
    if usage:
        body["usage"] = {"prompt_tokens": 30, "completion_tokens": 8}
    return httpx.Response(200, json=body)


async def test_it_sends_the_chat_request_and_reads_the_answer() -> None:
    seen: list[httpx.Request] = []

    def handle(r: httpx.Request) -> httpx.Response:
        seen.append(r)
        return ok()

    out = await provider(httpx.MockTransport(handle), api_key="k", json_mode=True).complete(
        request()
    )
    sent = json.loads(seen[0].content)
    assert str(seen[0].url) == "http://127.0.0.1:8000/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer k"
    assert sent["model"] == "qwen" and sent["max_tokens"] == 500 and sent["temperature"] == 0.0
    assert sent["messages"][0] == {"role": "system", "content": "SYSTEM"}
    assert sent["response_format"] == {"type": "json_object"}
    assert (out.text, out.input_tokens, out.output_tokens) == ('{"candidates": []}', 30, 8)
    assert out.token_counts_are_estimates is False


async def test_json_mode_and_the_key_are_only_sent_when_asked() -> None:
    seen: list[httpx.Request] = []

    def handle(r: httpx.Request) -> httpx.Response:
        seen.append(r)
        return ok(usage=False)

    out = await provider(httpx.MockTransport(handle)).complete(request())
    assert "response_format" not in json.loads(seen[0].content)
    assert "authorization" not in seen[0].headers
    assert out.token_counts_are_estimates is True


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text=SECRET),
        httpx.Response(200, text="not json " + SECRET),
        httpx.Response(200, json={"choices": []}),
        ok(finish="length"),
        ok(content="   "),
    ],
)
async def test_failures_are_errors_and_never_repeat_patient_text(response: httpx.Response) -> None:
    with pytest.raises(LLMError) as err:
        await provider(httpx.MockTransport(lambda r: response)).complete(request())
    assert SECRET not in str(err.value)


async def test_a_timeout_or_a_dead_server_is_a_plain_error() -> None:
    def slow(r: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("x " + SECRET)

    def down(r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("y " + SECRET)

    for handler, word in ((slow, "timed out"), (down, "unreachable")):
        with pytest.raises(LLMError, match=word) as err:
            await provider(httpx.MockTransport(handler)).complete(request())
        assert SECRET not in str(err.value)


def test_which_addresses_may_receive_patient_text() -> None:
    for good in (
        "https://llm.hospital.example/v1",
        "http://127.0.0.1:8000/v1",
        "http://localhost:11434/v1",
        "http://10.1.2.3:8000/v1",
        "http://192.168.1.5/v1",
    ):
        assert address_problem(good) is None, good
    for bad in (
        "http://8.8.8.8:8000/v1",
        "http://llm.example.com/v1",
        "ftp://x/v1",
        "nonsense",
        "",
    ):
        assert address_problem(bad), bad
    with pytest.raises(ValueError, match="address"):
        SelfHostedLLMProvider("http://8.8.8.8/v1", model="m")
    with pytest.raises(ValueError, match="model"):
        SelfHostedLLMProvider("http://127.0.0.1/v1", model="")


def test_settings_refuse_a_bad_address_or_a_missing_model() -> None:
    with pytest.raises(ValueError, match="SELF_HOSTED_LLM_URL"):
        Settings(self_hosted_llm_url="http://8.8.8.8/v1", self_hosted_llm_model="m")
    with pytest.raises(ValueError, match="MODEL"):
        Settings(self_hosted_llm_url="http://127.0.0.1:8000/v1")
    Settings(self_hosted_llm_url="http://127.0.0.1:8000/v1", self_hosted_llm_model="m")


def test_it_is_reachable_by_name_only_once_registered() -> None:
    from app.ai.llm import LLMUnavailable

    unregister("self_hosted")
    with pytest.raises(LLMUnavailable, match="SELF_HOSTED_LLM_URL"):
        get_llm("self_hosted", environment="production")
    register("self_hosted", lambda: provider())
    try:
        assert get_llm("self_hosted", environment="production").model == "qwen"
    finally:
        unregister("self_hosted")
