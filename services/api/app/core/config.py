from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET = "dev-only-secret-change-me-dev-only-secret"  # noqa: S105
_DEV_FIELD_KEY = "ZGV2LW9ubHktZmllbGQta2V5LTMyLWJ5dGVzLXh4eHg="  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AAROGYA_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://aarogya_app:aarogya_app@localhost:5432/aarogya"
    jwt_secret: str = _DEV_SECRET
    jwt_algorithm: str = "HS256"
    # Base64 of 32 random bytes. Encrypts sensitive identifiers (e.g. ABHA numbers) and keys
    # their blind index. Losing it makes those identifiers unrecoverable: back it up.
    field_encryption_key: str = _DEV_FIELD_KEY
    # Older keys, comma separated, kept only while data is re-encrypted after a rotation.
    field_encryption_previous_keys: str = ""
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=14, ge=1, le=90)
    max_failed_logins: int = Field(default=5, ge=3)
    lockout_minutes: int = Field(default=15, ge=1)
    cors_origins: list[str] = []
    log_level: str = "INFO"
    # Bearer token for GET /metrics. Empty: the endpoint is disabled in production and open in dev.
    metrics_token: str = ""
    max_request_bytes: int = Field(default=5_000_000, ge=10_000, le=50_000_000)
    # Speech. No default provider in production: a deployment must choose one deliberately.
    llm_provider: str = ""
    # Anthropic (Claude), official SDK (app/ai/anthropic_llm.py). Registered only with a key.
    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_model: str = "claude-opus-5-5"
    # A model you run yourself (vLLM, Ollama, ...): app/ai/self_hosted.py. Off without an address.
    self_hosted_llm_url: str = ""
    self_hosted_llm_model: str = ""
    self_hosted_llm_api_key: SecretStr = SecretStr("")
    self_hosted_llm_json_mode: bool = False
    embedding_provider: str = ""
    llm_timeout_seconds: float = Field(default=60.0, gt=0, le=120)
    ai_analyses_per_minute: int = Field(default=6, ge=1, le=60)
    speech_provider: str = ""
    # Sarvam AI streaming speech-to-text (see app/speech/sarvam.py). Registered only with a key.
    sarvam_api_key: SecretStr = SecretStr("")
    sarvam_model: str = "saaras:v4"
    sarvam_mode: Literal["transcribe", "verbatim", "translit", "codemix"] = "transcribe"
    # Live test: a fixed language wrote Hindi in Roman letters; auto-detect did better.
    sarvam_use_language_hint: bool = False
    # Per worker process, per minute; 0 turns a limit off. See app/core/ratelimit.py.
    login_attempts_per_minute_per_ip: int = 60
    patient_searches_per_minute_per_user: int = 60
    sarvam_url: str = "wss://api.sarvam.ai/speech-to-text/ws"
    # The same key serves Sarvam's REST services. Each is chosen explicitly: nothing is sent to
    # Sarvam unless its provider is set to "sarvam".
    sarvam_rest_url: str = "https://api.sarvam.ai"
    sarvam_llm_model: str = "sarvam-105b"
    translation_provider: str = ""  # "" (off) or "sarvam"
    tts_provider: str = ""  # "" (off) or "sarvam"
    speech_fallback_provider: str = ""
    speech_monitor_interval_seconds: float = Field(default=2.0, gt=0, le=30)
    speech_max_session_seconds: int = Field(default=3600, ge=60, le=14400)
    # Local development audio store only. Production uses encrypted S3-compatible storage (Phase 7).
    audio_store_path: str = "/tmp/aarogya-audio"  # noqa: S108

    @model_validator(mode="after")
    def _defaults_and_production_rules(self) -> "Settings":
        if self.environment != "production":
            self.speech_provider = self.speech_provider or "development"
            self.llm_provider = self.llm_provider or "development"
            self.embedding_provider = self.embedding_provider or "development"
        if self.self_hosted_llm_url:
            from app.ai.self_hosted import address_problem

            problem = address_problem(self.self_hosted_llm_url)
            if problem:
                raise ValueError(f"AAROGYA_SELF_HOSTED_LLM_URL {problem}")
            if not self.self_hosted_llm_model:
                raise ValueError("AAROGYA_SELF_HOSTED_LLM_MODEL is required with a model address")
        if self.environment == "production":
            if self.jwt_secret == _DEV_SECRET or len(self.jwt_secret) < 32:
                raise ValueError("AAROGYA_JWT_SECRET must be set to a strong secret in production")
            if not self.sarvam_rest_url.startswith("https://"):
                raise ValueError("AAROGYA_SARVAM_REST_URL must be https:// in production")
            if not self.sarvam_url.startswith("wss://"):
                raise ValueError("AAROGYA_SARVAM_URL must be a wss:// URL in production")
            if "*" in self.cors_origins:
                raise ValueError("AAROGYA_CORS_ORIGINS must list origins explicitly in production")
            if self.database_url.startswith("postgresql+psycopg://aarogya_app:aarogya_app@"):
                raise ValueError("AAROGYA_DATABASE_URL still uses the development password")
            if self.field_encryption_key == _DEV_FIELD_KEY:
                raise ValueError("AAROGYA_FIELD_ENCRYPTION_KEY must be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
