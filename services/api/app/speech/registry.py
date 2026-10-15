from collections.abc import Callable

from app.speech.dev_provider import NAME as DEV_NAME
from app.speech.dev_provider import DevelopmentSpeechProvider
from app.speech.provider import ProviderNotAvailable, SpeechProvider

# Adapters appear here only once they have been written against the vendor's documented API and
# verified. Names listed in PENDING give a precise error instead of a silent fallback.
_FACTORIES: dict[str, Callable[[], SpeechProvider]] = {DEV_NAME: DevelopmentSpeechProvider}
PENDING: dict[str, str] = {
    "sarvam": "Sarvam is built but not configured: set AAROGYA_SARVAM_API_KEY.",
    "azure": "No Azure Speech adapter has been built yet.",
    "google": "No Google Speech adapter has been built yet.",
    "deepgram": "No Deepgram adapter has been built yet.",
    "openai": "No OpenAI speech adapter has been built yet.",
    "bhashini": "No Bhashini adapter has been built yet.",
}


def register(name: str, factory: Callable[[], SpeechProvider]) -> None:
    _FACTORIES[name] = factory


def unregister(name: str) -> None:
    _FACTORIES.pop(name, None)


def get_provider(name: str, *, environment: str) -> SpeechProvider:
    name = name.strip().lower()
    if not name:
        raise ProviderNotAvailable("No speech provider is configured (AAROGYA_SPEECH_PROVIDER)")
    factory = _FACTORIES.get(name)
    if factory is None:
        raise ProviderNotAvailable(PENDING.get(name, f"Unknown speech provider '{name}'"))
    provider = factory()
    if provider.is_development and environment == "production":
        # Synthetic transcripts must never reach a real patient's record.
        raise ProviderNotAvailable("The development speech provider is disabled in production")
    return provider
