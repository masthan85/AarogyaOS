"""Two-factor sign-in with an authenticator app (TOTP) and single-use recovery codes."""

import hashlib
import secrets
import uuid

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import totp
from app.core.config import Settings
from app.core.context import RequestMeta
from app.core.crypto import crypto_from_settings
from app.core.errors import Conflict, NotFound, Unauthorized
from app.core.security import verify_password
from app.modules.audit.service import record_audit
from app.modules.identity.models import User

RECOVERY_CODES = 8


class MfaStatus(BaseModel):
    enabled: bool
    recovery_codes_remaining: int


class EnrolOut(BaseModel):
    secret: str
    otpauth_uri: str


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class ConfirmOut(BaseModel):
    recovery_codes: list[str]


class DisableIn(BaseModel):
    password: str = Field(max_length=200)
    code: str = Field(min_length=6, max_length=20)


def _context(user: User) -> str:
    return f"mfa:{user.id}"


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().lower().replace("-", "").encode()).hexdigest()


def _audit(session: Session, meta: RequestMeta, user: User, action: str, reason: str = "") -> None:
    record_audit(
        session,
        meta,
        org_id=user.organisation_id,
        actor_user_id=user.id,
        action=action,
        resource_type="user",
        resource_id=user.id,
        reason=reason or None,
    )


def status(user: User) -> MfaStatus:
    return MfaStatus(
        enabled=user.mfa_enabled, recovery_codes_remaining=len(user.mfa_recovery or [])
    )


def enrol(session: Session, settings: Settings, meta: RequestMeta, user: User) -> EnrolOut:
    if user.mfa_enabled:
        raise Conflict("Two-factor sign-in is already on. Turn it off first to enrol again.")
    secret = totp.new_secret()
    user.mfa_secret = crypto_from_settings(settings).encrypt(secret, context=_context(user))
    session.flush()
    _audit(session, meta, user, "MFA_ENROLMENT_STARTED")
    session.commit()
    return EnrolOut(secret=secret, otpauth_uri=totp.provisioning_uri(secret, user.email))


def _secret(settings: Settings, user: User) -> str:
    assert user.mfa_secret is not None
    return crypto_from_settings(settings).decrypt(user.mfa_secret, context=_context(user))


def confirm(
    session: Session, settings: Settings, meta: RequestMeta, user: User, code: str
) -> ConfirmOut:
    if user.mfa_enabled:
        raise Conflict("Two-factor sign-in is already on")
    if not user.mfa_secret:
        raise Conflict("Start enrolment first")
    step = totp.verify(_secret(settings, user), code)
    if step is None:
        raise Unauthorized("That code is not right. Check the time on your phone and try again.")
    codes = [
        f"{secrets.token_hex(5)[:5]}-{secrets.token_hex(5)[:5]}" for _ in range(RECOVERY_CODES)
    ]
    user.mfa_recovery = [_hash(c) for c in codes]
    user.mfa_last_step = step
    user.mfa_enabled = True
    _audit(session, meta, user, "MFA_ENABLED")
    session.commit()
    return ConfirmOut(recovery_codes=codes)


def accept_login_code(
    session: Session, settings: Settings, meta: RequestMeta, user: User, code: str
) -> bool:
    """True for a fresh authenticator code or an unused recovery code (which is then spent)."""
    if not user.mfa_secret:
        return False
    step = totp.verify(_secret(settings, user), code)
    if step is not None and (user.mfa_last_step is None or step > user.mfa_last_step):
        user.mfa_last_step = step  # a code works once
        return True
    digest = _hash(code)
    remaining = list(user.mfa_recovery or [])
    if digest in remaining:
        remaining.remove(digest)
        user.mfa_recovery = remaining
        _audit(session, meta, user, "MFA_RECOVERY_CODE_USED")
        return True
    return False


def disable(
    session: Session, settings: Settings, meta: RequestMeta, user: User, password: str, code: str
) -> None:
    if not user.mfa_enabled:
        raise Conflict("Two-factor sign-in is not on")
    if not verify_password(password, user.password_hash):
        raise Unauthorized("That password is not right")
    if not accept_login_code(session, settings, meta, user, code):
        raise Unauthorized("That code is not right")
    _clear(user)
    _audit(session, meta, user, "MFA_DISABLED")
    session.commit()


def _clear(user: User) -> None:
    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_last_step = None
    user.mfa_recovery = []


def admin_reset(
    session: Session, meta: RequestMeta, actor_id: uuid.UUID, user: User | None
) -> None:
    """For someone who lost their phone and recovery codes. Audited against the target user."""
    if user is None:
        raise NotFound("User not found")
    _clear(user)
    record_audit(
        session,
        meta,
        org_id=user.organisation_id,
        actor_user_id=actor_id,
        action="MFA_RESET_BY_ADMIN",
        resource_type="user",
        resource_id=user.id,
    )
    session.commit()
