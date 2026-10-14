"""Anthropic (Claude) adapter for the LLMProvider interface, via the official `anthropic` SDK.

It only turns a rendered prompt into text. Everything that makes the result trustworthy (strict JSON
parsing, schema validation, exact-quote grounding, safety rules, clinician review) still happens in
our code afterwards, exactly as for any other provider.

Behaviour that follows the current Claude API for these models:
* No `temperature` is sent: it is rejected on the current models, and nothing here assumes
  deterministic output.
* Thinking is left at the model's default (adaptive). Thinking tokens count against `max_tokens`,
  so the cap is raised to leave room for the answer.
* A `refusal` stop (the vendor's safety classifier declined) and a truncated answer are errors,
  never partial results: a half-finished JSON object must not be "repaired".
* Vendor error text and request content never reach exceptions or logs; only a short status code.

**Not run against the real API in this repository** (no key here): tested with a stub client.
Before real patient data: a signed data-processing agreement (no training on our data, retention
terms), a data-residency decision (check where the endpoint processes data), and an extraction
evaluation on clinician-labelled transcripts. Do not set `ANTHROPIC_LOG=debug` outside development:
it logs requests.
"""

import time
from typing import Any

import anthropic

from app.ai.llm import LLMError, LLMRequest, LLMResponse

NAME = "anthropic"
MIN_MAX_TOKENS = 16_000  # room for adaptive thinking plus the answer


class AnthropicLLMProvider:
    name = NAME
    is_development = False

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "claude-opus-5-5",
        timeout_seconds: float = 60.0,
        client: Any = None,
    ) -> None:
        if not api_key and client is None:
            raise ValueError("An Anthropic API key is required")
        self.model = model
        # max_retries=0: the caller bounds total time with its own timeout, so no hidden retries.
        self._client = client or anthropic.AsyncAnthropic(
            api_key=api_key, timeout=timeout_seconds, max_retries=0
        )

    def __repr__(self) -> str:  # never show the key
        return f"AnthropicLLMProvider(model={self.model!r})"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        started = time.monotonic()
        try:
            resp = await self._client.messages.create(
                model=self.model,
                max_tokens=max(request.max_tokens, MIN_MAX_TOKENS),
                system=request.system,
                messages=[{"role": "user", "content": request.prompt}],
            )
        except anthropic.APITimeoutError:
            raise LLMError("anthropic request timed out") from None
        except anthropic.APIConnectionError:
            raise LLMError("anthropic is unreachable") from None
        except anthropic.APIStatusError as exc:
            raise LLMError(f"anthropic returned status {exc.status_code}") from None

        stop = getattr(resp, "stop_reason", None)
        if stop == "refusal":
            raise LLMError("anthropic declined the request")
        if stop == "max_tokens":
            raise LLMError("anthropic output was cut off")
        text = "".join(
            str(getattr(b, "text", "")) for b in resp.content if getattr(b, "type", None) == "text"
        )
        if not text.strip():
            raise LLMError("anthropic returned no text")
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text,
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            latency_ms=int((time.monotonic() - started) * 1000),
            token_counts_are_estimates=False,
        )
