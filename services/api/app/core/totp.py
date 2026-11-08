"""Time-based one-time passwords (RFC 6238) without a third-party dependency.

SHA-1, six digits and a 30 second step are what authenticator apps expect, so those are fixed.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1  # accept the previous and next step to allow for clock drift


def new_secret() -> str:
    """A random 160-bit secret as unpadded base32, the form authenticator apps take."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _hotp(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()  # noqa: S324
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def code_at(secret: str, step: int) -> str:
    return _hotp(secret, step)


def verify(secret: str, code: str, *, now: float | None = None) -> int | None:
    """The time step the code belongs to, or None. Callers must refuse a step they have seen."""
    code = code.strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    step = current_step(now)
    matched: int | None = None
    for candidate in range(step - WINDOW, step + WINDOW + 1):
        if hmac.compare_digest(_hotp(secret, candidate), code):
            matched = candidate
    return matched


def provisioning_uri(secret: str, account: str, issuer: str = "AarogyaOS") -> str:
    label = quote(f"{issuer}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={STEP_SECONDS}"
