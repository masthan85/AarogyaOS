"""LLM provider abstraction.

Business logic never imports a vendor SDK. A provider turns a request into text; everything that
makes the result *trustworthy* (schema validation, evidence checks, safety rules) happens in our
code afterwards, so a model can be swapped or misbehave without weakening those controls.

Like `app.speech`, this package imports nothing from the HTTP or database layers.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class LLMUnavailable(Exception):
    """The configured provider is unknown, unbuilt, unconfigured or not allowed here."""


class LLMError(Exception):
    """The provider failed or timed out. The message must not contain patient content."""


@dataclass(frozen=True)
class LLMRequest:
    task: str  # e.g. "clinical_extraction"
    prompt_version: str
    system: str
    prompt: str  # fully rendered text for real models
    # The same content as structured data. Real providers ignore it; the development provider
    # reads it so it needs no text parsing.
    payload: dict[str, Any] = field(default_factory=dict)
    max_tokens: int = 1500
    temperature: float = 0.0


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    token_counts_are_estimates: bool = False


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str
    # True for adapters that do not call a real model. Refused in production.
    is_development: bool

    async def complete(self, request: LLMRequest) -> LLMResponse: ...
