import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings

_hasher = PasswordHasher()
# Verified against when a user does not exist so response timing doesn't reveal accounts.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    org_id: uuid.UUID | None
    session_id: uuid.UUID


class InvalidToken(Exception):
    pass


def issue_access_token(
    settings: Settings, user_id: uuid.UUID, org_id: uuid.UUID | None, session_id: uuid.UUID
) -> tuple[str, int]:
    now = datetime.now(UTC)
    ttl = timedelta(minutes=settings.access_token_minutes)
    payload = {
        "sub": str(user_id),
        "org": str(org_id) if org_id else None,
        "sid": str(session_id),
        "typ": "access",
        "iat": now,
        "exp": now + ttl,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(ttl.total_seconds())


def decode_access_token(settings: Settings, token: str) -> TokenClaims:
    try:
        data = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "typ"]},
        )
        if data["typ"] != "access":
            raise InvalidToken
        org = data.get("org")
        return TokenClaims(
            user_id=uuid.UUID(data["sub"]),
            org_id=uuid.UUID(org) if org else None,
            session_id=uuid.UUID(data["sid"]),
        )
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise InvalidToken from exc
