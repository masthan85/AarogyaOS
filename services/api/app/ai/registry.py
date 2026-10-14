from collections.abc import Callable

from app.ai.dev_llm import NAME as DEV_NAME
from app.ai.dev_llm import DevelopmentLLMProvider
from app.ai.llm import LLMProvider, LLMUnavailable

_FACTORIES: dict[str, Callable[[], LLMProvider]] = {DEV_NAME: DevelopmentLLMProvider}
# Named so the error is specific. An adapter is added only after its API has been read and its
# data-processing terms (residency, retention, training opt-out) have been agreed in writing.
PENDING: dict[str, str] = {
    "anthropic": (
        "Anthropic is built but not configured: set AAROGYA_ANTHROPIC_API_KEY (and have a signed "
        "data-processing agreement before sending patient data)."
    ),
    "openai": "No OpenAI adapter has been built yet.",
    "azure_openai": "No Azure OpenAI adapter has been built yet.",
    "google": "No Google adapter has been built yet.",
    "self_hosted": "No self-hosted model adapter has been built yet.",
}


def register(name: str, factory: Callable[[], LLMProvider]) -> None:
    _FACTORIES[name] = factory


def unregister(name: str) -> None:
    _FACTORIES.pop(name, None)


def get_llm(name: str, *, environment: str) -> LLMProvider:
    name = name.strip().lower()
    if not name:
        raise LLMUnavailable("No LLM provider is configured (AAROGYA_LLM_PROVIDER)")
    factory = _FACTORIES.get(name)
    if factory is None:
        raise LLMUnavailable(PENDING.get(name, f"Unknown LLM provider '{name}'"))
    provider = factory()
    if provider.is_development and environment == "production":
        raise LLMUnavailable("The development LLM is disabled in production")
    return provider
