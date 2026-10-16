"""Sarvam AI services behind our provider interfaces: translation, text-to-speech and chat.

All three use the official `sarvamai` SDK (REST). Each call runs the SDK's blocking client in a
worker thread. Vendor error text is never propagated (only a status code), and the API key is never
logged or shown. Speech-to-text streaming has its own adapter in `app.speech.sarvam`.

None of this has been run against the live service from this repository (the build environment
cannot reach api.sarvam.ai); it is tested against a local HTTP server that speaks the SDK's wire
format. Run it with a key before relying on it.

What we do NOT use, and why: voice cloning and dubbing (no clinical use; cloning a voice is an
identity-and-consent hazard); the beta realtime endpoint (the generally-available one is enough);
batch speech-to-text, document intelligence and document translation (they need stored files and
their output formats were not verifiable here; see docs/SARVAM.md).
"""

import asyncio
import base64
import io
import re
import time
import wave
from typing import Any

from sarvamai import SarvamAI
from sarvamai.core.api_error import ApiError
from sarvamai.environment import SarvamAIEnvironment

from app.ai.knowledge import NotAvailable
from app.ai.llm import LLMError, LLMRequest, LLMResponse

PRODUCTION_URL = "https://api.sarvam.ai"
TRANSLATE_MODEL = "sarvam-translate:v1"  # all 22 scheduled languages, formal register only
TRANSLATE_CHUNK = 1800  # the model's limit is 2000 characters per request
TTS_CHUNK = 2000  # bulbul:v3 allows 2500
TRANSLATE_LANGUAGES = frozenset(
    "en-IN hi-IN bn-IN gu-IN kn-IN ml-IN mr-IN od-IN pa-IN ta-IN te-IN as-IN brx-IN doi-IN kok-IN "
    "ks-IN mai-IN mni-IN ne-IN sa-IN sat-IN sd-IN ur-IN".split()
)
TTS_LANGUAGES = frozenset(
    "en-IN hi-IN bn-IN gu-IN kn-IN ml-IN mr-IN od-IN pa-IN ta-IN te-IN".split()
)


def make_client(api_key: str, *, base_url: str = PRODUCTION_URL, timeout: float = 60.0) -> SarvamAI:
    env = SarvamAIEnvironment(base=base_url, creative=base_url, production=base_url)
    return SarvamAI(environment=env, api_subscription_key=api_key, timeout=timeout)


def _status(exc: Exception) -> str:
    code = getattr(exc, "status_code", None)
    return f"status {code}" if code else type(exc).__name__


def split_text(text: str, limit: int) -> list[str]:
    """Split on line breaks, then sentence ends, never mid-word, keeping chunks under `limit`."""
    chunks: list[str] = []
    for paragraph in text.split("\n"):
        if len(paragraph) <= limit:
            chunks.append(paragraph)
            continue
        current = ""
        for sentence in re.split(r"(?<=[.!?।])\s+", paragraph):
            while len(sentence) > limit:  # a single enormous sentence: cut on a space
                cut = sentence.rfind(" ", 0, limit)
                if cut <= 0:
                    cut = limit
                chunks.append(sentence[:cut])
                sentence = sentence[cut:].lstrip()
            if current and len(current) + 1 + len(sentence) > limit:
                chunks.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            chunks.append(current)
    return chunks


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def numbers_in(text: str) -> list[str]:
    return sorted(_NUMBER.findall(text))


class SarvamTranslationProvider:
    available = True

    def __init__(
        self, api_key: str, *, base_url: str = PRODUCTION_URL, timeout: float = 60.0
    ) -> None:
        self._client = make_client(api_key, base_url=base_url, timeout=timeout)

    def __repr__(self) -> str:
        return "SarvamTranslationProvider()"

    def _one(self, text: str, source: str, target: str) -> str:
        if not text.strip():
            return text
        try:
            r = self._client.text.translate(
                input=text,
                source_language_code=source,
                target_language_code=target,
                model=TRANSLATE_MODEL,
                mode="formal",
                numerals_format="international",  # keep 0-9: a dose must not change its digits
            )
        except ApiError as exc:
            raise NotAvailable(f"Sarvam translation failed ({_status(exc)})") from None
        except Exception:  # noqa: BLE001  (network errors etc.: never expose details)
            raise NotAvailable("Sarvam translation is unreachable") from None
        return str(r.translated_text)

    async def translate(self, text: str, source: str, target: str) -> str:
        if source not in TRANSLATE_LANGUAGES or target not in TRANSLATE_LANGUAGES:
            raise NotAvailable(f"Translation from {source} to {target} is not supported")
        parts = split_text(text, TRANSLATE_CHUNK)
        out = [await asyncio.to_thread(self._one, p, source, target) for p in parts]
        return "\n".join(out)


class SarvamTTSProvider:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = PRODUCTION_URL,
        timeout: float = 60.0,
        model: str = "bulbul:v3",
    ) -> None:
        self._client = make_client(api_key, base_url=base_url, timeout=timeout)
        self._model = model

    def __repr__(self) -> str:
        return f"SarvamTTSProvider(model={self._model!r})"

    def supports(self, language: str) -> bool:
        return language in TTS_LANGUAGES

    def _one(self, text: str, language: str) -> bytes:
        try:
            r = self._client.text_to_speech.convert(
                text=text, language_code=language, model=self._model, output_audio_codec="wav"
            )
        except ApiError as exc:
            raise NotAvailable(f"Sarvam text-to-speech failed ({_status(exc)})") from None
        except Exception:  # noqa: BLE001
            raise NotAvailable("Sarvam text-to-speech is unreachable") from None
        if not r.audios:
            raise NotAvailable("Sarvam text-to-speech returned no audio")
        return base64.b64decode(r.audios[0])

    async def synthesize(self, text: str, language: str) -> bytes:
        """WAV audio for `text`. Long text is spoken in pieces and joined into one file."""
        if not self.supports(language):
            raise NotAvailable(f"Spoken output is not available in {language}")
        pieces = [p for p in split_text(text, TTS_CHUNK) if p.strip()]
        if not pieces:
            raise NotAvailable("There is nothing to read aloud")
        wavs = [await asyncio.to_thread(self._one, p, language) for p in pieces]
        return join_wav(wavs)


def join_wav(wavs: list[bytes]) -> bytes:
    """Concatenate WAV files that share one format into a single WAV."""
    if len(wavs) == 1:
        return wavs[0]
    out = io.BytesIO()
    params: Any = None
    with wave.open(out, "wb") as dest:
        for blob in wavs:
            with wave.open(io.BytesIO(blob), "rb") as src:
                if params is None:
                    params = src.getparams()
                    dest.setparams(params)
                elif src.getparams()[:3] != params[:3]:
                    raise NotAvailable("Sarvam returned audio in mixed formats")
                dest.writeframes(src.readframes(src.getnframes()))
    return out.getvalue()


class SarvamLLMProvider:
    """Sarvam's chat models as an LLMProvider. Output still passes through every guardrail."""

    name = "sarvam"
    is_development = False

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "sarvam-105b",
        base_url: str = PRODUCTION_URL,
        timeout: float = 60.0,
    ) -> None:
        if not api_key:
            raise ValueError("A Sarvam API key is required")
        self.model = model
        self._client = make_client(api_key, base_url=base_url, timeout=timeout)

    def __repr__(self) -> str:
        return f"SarvamLLMProvider(model={self.model!r})"

    def _call(self, request: LLMRequest) -> Any:
        return self._client.chat.completions(
            model=self.model,
            messages=[
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
            temperature=request.temperature,
            max_tokens=max(request.max_tokens, 4000),  # a reasoning model spends tokens thinking
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        started = time.monotonic()
        try:
            resp = await asyncio.to_thread(self._call, request)
        except ApiError as exc:
            raise LLMError(f"sarvam returned {_status(exc)}") from None
        except Exception:  # noqa: BLE001
            raise LLMError("sarvam is unreachable") from None
        if not resp.choices:
            raise LLMError("sarvam returned no answer")
        choice = resp.choices[0]
        if getattr(choice, "finish_reason", None) == "length":
            raise LLMError("sarvam output was cut off")
        message = choice.message
        if getattr(message, "refusal", None):
            raise LLMError("sarvam declined the request")
        text = message.content or ""
        if not text.strip():
            raise LLMError("sarvam returned no text")
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text,
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            latency_ms=int((time.monotonic() - started) * 1000),
            token_counts_are_estimates=False,
        )
