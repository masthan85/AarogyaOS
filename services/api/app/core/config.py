from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
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
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=14, ge=1, le=90)
    max_failed_logins: int = Field(default=5, ge=3)
    lockout_minutes: int = Field(default=15, ge=1)
    cors_origins: list[str] = []
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _reject_unsafe_production(self) -> "Settings":
        if self.environment == "production":
            if self.jwt_secret == _DEV_SECRET or len(self.jwt_secret) < 32:
                raise ValueError("AAROGYA_JWT_SECRET must be set to a strong secret in production")
            if self.field_encryption_key == _DEV_FIELD_KEY:
                raise ValueError("AAROGYA_FIELD_ENCRYPTION_KEY must be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
