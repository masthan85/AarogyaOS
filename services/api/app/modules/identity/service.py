import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.context import Principal, RequestMeta
from app.core.db import set_tenant
from app.core.errors import AppError, Conflict, Forbidden, NotFound, Unauthorized
from app.core.security import (
    hash_password,
    hash_token,
    issue_access_token,
    new_refresh_token,
    verify_password,
)
from app.modules.audit.service import record_audit
from app.modules.identity.models import RefreshToken, Role, RolePermission, User, UserRole
from app.modules.identity.schemas import TokenPair, UserOut
from app.modules.tenancy.models import Organisation

_BAD_CREDENTIALS = "Invalid credentials"


def _now() -> datetime:
    return datetime.now(UTC)


def normalise_email(email: str) -> str:
    return email.strip().lower()


def _issue_pair(
    session: Session, settings: Settings, user: User, family_id: uuid.UUID
) -> TokenPair:
    raw, hashed = new_refresh_token()
    session.add(
        RefreshToken(
            organisation_id=user.organisation_id,
            user_id=user.id,
            family_id=family_id,
            token_hash=hashed,
            expires_at=_now() + timedelta(days=settings.refresh_token_days),
        )
    )
    access, ttl = issue_access_token(settings, user.id, user.organisation_id, family_id)
    return TokenPair(access_token=access, refresh_token=raw, expires_in=ttl)


def login(
    session: Session,
    settings: Settings,
    meta: RequestMeta,
    *,
    organisation_slug: str | None,
    email: str,
    password: str,
) -> TokenPair:
    org_id: uuid.UUID | None = None
    if organisation_slug:
        org = session.scalar(
            select(Organisation).where(
                Organisation.slug == organisation_slug.lower(), Organisation.status == "ACTIVE"
            )
        )
        if org is None:
            verify_password(password, None)
            raise Unauthorized(_BAD_CREDENTIALS)
        org_id = org.id

    user = session.scalar(
        select(User).where(
            User.organisation_id == org_id if org_id else User.organisation_id.is_(None),
            User.email == normalise_email(email),
        )
    )
    now = _now()
    if user is None:
        verify_password(password, None)
        raise Unauthorized(_BAD_CREDENTIALS)

    if user.locked_until and user.locked_until > now:
        record_audit(
            session,
            meta,
            org_id=org_id,
            actor_user_id=user.id,
            action="LOGIN_BLOCKED",
            resource_type="user",
            resource_id=user.id,
            outcome="DENIED",
            reason="locked",
        )
        session.commit()
        raise Unauthorized(_BAD_CREDENTIALS)

    if not user.is_active or not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_login_count = 0
        record_audit(
            session,
            meta,
            org_id=org_id,
            actor_user_id=user.id,
            action="LOGIN_FAILED",
            resource_type="user",
            resource_id=user.id,
            outcome="DENIED",
        )
        session.commit()
        raise Unauthorized(_BAD_CREDENTIALS)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    pair = _issue_pair(session, settings, user, uuid.uuid4())
    record_audit(
        session,
        meta,
        org_id=org_id,
        actor_user_id=user.id,
        action="LOGIN_SUCCESS",
        resource_type="user",
        resource_id=user.id,
    )
    session.commit()
    return pair


def refresh(session: Session, settings: Settings, meta: RequestMeta, raw_token: str) -> TokenPair:
    token = session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw_token))
        .with_for_update()
    )
    now = _now()
    if token is None:
        raise Unauthorized("Invalid refresh token")
    if token.used_at is not None or token.revoked_at is not None:
        # A rotated/revoked token came back: assume theft and kill the whole session family.
        _revoke_family(session, token.family_id, now)
        record_audit(
            session,
            meta,
            org_id=token.organisation_id,
            actor_user_id=token.user_id,
            action="REFRESH_REUSE_DETECTED",
            resource_type="session",
            outcome="DENIED",
        )
        session.commit()
        raise Unauthorized("Invalid refresh token")
    if token.expires_at <= now:
        raise Unauthorized("Invalid refresh token")
    user = session.get(User, token.user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Invalid refresh token")
    token.used_at = now
    pair = _issue_pair(session, settings, user, token.family_id)
    session.commit()
    return pair


def logout(session: Session, meta: RequestMeta, raw_token: str) -> None:
    token = session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    )
    if token is None:
        return
    _revoke_family(session, token.family_id, _now())
    record_audit(
        session,
        meta,
        org_id=token.organisation_id,
        actor_user_id=token.user_id,
        action="LOGOUT",
        resource_type="session",
    )
    session.commit()


def _revoke_family(session: Session, family_id: uuid.UUID, now: datetime) -> None:
    session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


# ---- staff user management -------------------------------------------------


def _roles_by_key(session: Session, keys: list[str]) -> list[Role]:
    unique = sorted(set(keys))
    roles = list(session.scalars(select(Role).where(Role.key.in_(unique))))
    if len(roles) != len(unique):
        raise AppError("Unknown role")
    return roles


def _guard_assignable(principal: Principal, roles: list[Role]) -> None:
    # Prevents privilege escalation: tenant admins can never mint platform administrators.
    if any(r.is_platform for r in roles) and not principal.is_platform:
        raise Forbidden("Role cannot be assigned")


def _out(session: Session, user: User) -> UserOut:
    keys = list(
        session.scalars(
            select(Role.key)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        )
    )
    out = UserOut.model_validate(user)
    out.roles = sorted(keys)
    return out


def create_user(
    session: Session,
    principal: Principal,
    *,
    email: str,
    full_name: str,
    password: str,
    role_keys: list[str],
    preferred_language: str,
) -> UserOut:
    if principal.org_id is None:
        raise Forbidden("Platform administrators create users through organisation setup")
    roles = _roles_by_key(session, role_keys)
    _guard_assignable(principal, roles)
    user = User(
        organisation_id=principal.org_id,
        email=normalise_email(email),
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        preferred_language=preferred_language,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise Conflict("A user with this email already exists") from exc
    for role in roles:
        session.add(UserRole(user_id=user.id, role_id=role.id, organisation_id=principal.org_id))
    record_audit(
        session,
        principal.meta,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        action="USER_CREATED",
        resource_type="user",
        resource_id=user.id,
        after={"email": user.email, "roles": sorted(r.key for r in roles)},
    )
    session.commit()
    return _out(session, user)


def list_users(session: Session, principal: Principal, limit: int, offset: int) -> list[UserOut]:
    users = session.scalars(
        select(User)
        .where(User.organisation_id == principal.org_id)
        .order_by(User.full_name)
        .limit(limit)
        .offset(offset)
    )
    return [_out(session, u) for u in users]


def _get_user(session: Session, principal: Principal, user_id: uuid.UUID) -> User:
    user = session.scalar(
        select(User).where(User.id == user_id, User.organisation_id == principal.org_id)
    )
    if user is None:
        raise NotFound("User not found")
    return user


def get_user(session: Session, principal: Principal, user_id: uuid.UUID) -> UserOut:
    return _out(session, _get_user(session, principal, user_id))


def set_roles(
    session: Session, principal: Principal, user_id: uuid.UUID, role_keys: list[str]
) -> UserOut:
    user = _get_user(session, principal, user_id)
    roles = _roles_by_key(session, role_keys)
    _guard_assignable(principal, roles)
    before = _out(session, user).roles
    session.query(UserRole).filter(UserRole.user_id == user.id).delete()
    for role in roles:
        session.add(UserRole(user_id=user.id, role_id=role.id, organisation_id=principal.org_id))
    record_audit(
        session,
        principal.meta,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        action="USER_ROLES_CHANGED",
        resource_type="user",
        resource_id=user.id,
        before={"roles": before},
        after={"roles": sorted(r.key for r in roles)},
    )
    session.commit()
    return _out(session, user)


def deactivate_user(session: Session, principal: Principal, user_id: uuid.UUID) -> UserOut:
    user = _get_user(session, principal, user_id)
    if user.id == principal.user_id:
        raise AppError("You cannot deactivate your own account")
    if user.is_active:
        user.is_active = False
        _revoke_user_sessions(session, user.id)
        record_audit(
            session,
            principal.meta,
            org_id=principal.org_id,
            actor_user_id=principal.user_id,
            action="USER_DEACTIVATED",
            resource_type="user",
            resource_id=user.id,
            before={"is_active": True},
            after={"is_active": False},
        )
        session.commit()
    return _out(session, user)


def _revoke_user_sessions(session: Session, user_id: uuid.UUID) -> None:
    session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )


def list_roles(session: Session) -> list[tuple[Role, list[str]]]:
    out = []
    for role in session.scalars(select(Role).where(Role.is_platform.is_(False)).order_by(Role.key)):
        perms = list(
            session.scalars(
                select(RolePermission.permission_key).where(RolePermission.role_id == role.id)
            )
        )
        out.append((role, sorted(perms)))
    return out


def create_org_admin(
    session: Session,
    org_id: uuid.UUID,
    platform_user_id: uuid.UUID,
    meta: RequestMeta,
    *,
    email: str,
    full_name: str,
    password: str,
) -> User:
    """Used by organisation setup; runs inside the new organisation's tenant context."""
    set_tenant(session, org_id)
    role = session.scalar(select(Role).where(Role.key == "hospital_admin"))
    if role is None:
        raise AppError("Reference data not seeded")
    user = User(
        organisation_id=org_id,
        email=normalise_email(email),
        full_name=full_name.strip(),
        password_hash=hash_password(password),
    )
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role_id=role.id, organisation_id=org_id))
    record_audit(
        session,
        meta,
        org_id=org_id,
        actor_user_id=platform_user_id,
        action="USER_CREATED",
        resource_type="user",
        resource_id=user.id,
        after={"email": user.email, "roles": ["hospital_admin"]},
    )
    return user
