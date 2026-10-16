"""Which optional vendor services are connected, decided only by explicit configuration."""

from typing import Any

from app.ai.knowledge import NotAvailable, NullTranslationProvider, TranslationProvider
from app.ai.sarvam import SarvamTranslationProvider, SarvamTTSProvider
from app.core.config import Settings


def get_translator(settings: Settings) -> TranslationProvider:
    """Sarvam if chosen and keyed; otherwise a provider that reports itself unavailable."""
    key = settings.sarvam_api_key.get_secret_value()
    if settings.translation_provider == "sarvam" and key:
        return SarvamTranslationProvider(key, base_url=settings.sarvam_rest_url)
    return NullTranslationProvider()


def get_tts(settings: Settings) -> Any:
    key = settings.sarvam_api_key.get_secret_value()
    if settings.tts_provider == "sarvam" and key:
        return SarvamTTSProvider(key, base_url=settings.sarvam_rest_url)
    raise NotAvailable("No text-to-speech service is connected")
