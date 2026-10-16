"""A language model you run yourself, reached through the common chat-completions interface.

vLLM, Ollama, llama.cpp's server and several others all speak this interface, so one adapter covers
them. Nothing leaves the machine or network you point it at, which lets a hospital that cannot send
patient text to a vendor still use the assistant. Everything that makes a result trustworthy (strict
JSON parsing, schema checks, exact-quote grounding, safety rules, clinician review) still happens in
our code afterwards, exactly as for any other provider.

Not run against a real server in this repository: tested against a fake one. Which model to use is a
separate question that needs an evaluation on clinician-labelled transcripts before real use.

Only the address the owner configures is ever contacted, over `https`, or plain `http` for a
loopback or private-network address. Vendor error text and request content never reach exceptions
or logs.
"""

import ipaddress
import time
from urllib.parse import urlparse

import httpx

from app.ai.llm import LLMError, LLMRequest, LLMResponse

NAME = "self_hosted"


def address_problem(url: str) -> str | None:
    """Why this address is not acceptable for patient text, or None if it is."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return "must be an http(s) address"
    if parts.scheme == "https":
        return None
    host = parts.hostname
    if host == "localhost":
        return None
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "must use https unless it is localhost or a private network address"
    if ip.is_loopback or ip.is_private:
        return None
    return "plain http is only allowed for localhost or a private network address"


class SelfHostedLLMProvider:
    name = NAME
    is_development = False

    def __init__(
        self,
        base_url: str,
        *,
        model: str,
        api_key: str = "",
        timeout_seconds: float = 60.0,
        json_mode: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        problem = address_problem(base_url)
        if problem:
            raise ValueError(f"The self-hosted model address {problem}")
        if not model:
            raise ValueError("A model name is required for the self-hosted model")
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout_seconds
        self._json_mode = json_mode
        self._transport = transport

    def __repr__(self) -> str:
        return f"SelfHostedLLMProvider(model={self.model!r})"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        body: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if self._json_mode:
            body["response_format"] = {"type": "json_object"}
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as http:
                resp = await http.post(self._url, json=body, headers=self._headers)
        except httpx.TimeoutException:
            raise LLMError("the self-hosted model timed out") from None
        except httpx.HTTPError:
            raise LLMError("the self-hosted model is unreachable") from None
        if resp.status_code != 200:
            raise LLMError(f"the self-hosted model returned {resp.status_code}")
        try:
            data = resp.json()
            choice = data["choices"][0]
            text = choice["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMError("the self-hosted model sent an answer in an unexpected shape") from None
        if choice.get("finish_reason") == "length":
            raise LLMError("the self-hosted model's output was cut off")
        if not str(text).strip():
            raise LLMError("the self-hosted model returned no text")
        usage = data.get("usage") or {}
        return LLMResponse(
            text=str(text),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=int((time.monotonic() - started) * 1000),
            # Servers that omit usage leave zeros, which are not counts of anything.
            token_counts_are_estimates=not usage,
        )
