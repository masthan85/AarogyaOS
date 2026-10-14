from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import exists, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.context import Principal, RequestMeta
from app.core.crypto import FieldCrypto
from app.core.db import set_tenant
from app.core.errors import Forbidden, Unauthorized
from app.core.security import InvalidToken, TokenClaims, decode_access_token
from app.modules.audit.service import record_audit
from app.modules.identity.models import RefreshToken, Role, RolePermission, User, UserRole

_bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_sessionmaker(request: Request) -> "sessionmaker[Session]":
    sm: sessionmaker[Session] = request.app.state.sessionmaker
    return sm


def get_crypto(request: Request) -> FieldCrypto:
    crypto: FieldCrypto = request.app.state.crypto
    return crypto


def get_meta(request: Request) -> RequestMeta:
    return RequestMeta.from_request(request)


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionMakerDep = Annotated["sessionmaker[Session]", Depends(get_sessionmaker)]
MetaDep = Annotated[RequestMeta, Depends(get_meta)]
CryptoDep = Annotated[FieldCrypto, Depends(get_crypto)]


def get_claims(
    settings: SettingsDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> TokenClaims:
    if creds is None:
        raise Unauthorized("Authentication required")
    try:
        return decode_access_token(settings, creds.credentials)
    except InvalidToken as exc:
        raise Unauthorized("Invalid or expired token") from exc


def system_session(sm: SessionMakerDep) -> Iterator[Session]:
    """Unscoped session for the login/refresh flows, which run before a tenant is known."""
    session = sm()
    set_tenant(session, None, bypass=True)
    try:
        yield session
    finally:
        session.close()


def tenant_session(
    sm: SessionMakerDep, claims: Annotated[TokenClaims, Depends(get_claims)]
) -> Iterator[Session]:
    """Session whose rows are restricted by Postgres RLS to the caller's organisation."""
    session = sm()
    set_tenant(session, claims.org_id, platform=claims.org_id is None)
    try:
        yield session
    finally:
        session.close()


SystemDb = Annotated[Session, Depends(system_session)]
TenantDb = Annotated[Session, Depends(tenant_session)]


def build_principal(db: Session, claims: TokenClaims, meta: RequestMeta) -> Principal:
    """Resolve token claims into a live principal. Shared by HTTP and WebSocket entry points."""
    user = db.get(User, claims.user_id)
    if user is None or not user.is_active or user.organisation_id != claims.org_id:
        raise Unauthorized("Account unavailable")
    # A logged-out or revoked session must stop working immediately, not at token expiry.
    live = db.scalar(
        select(
            exists().where(
                RefreshToken.family_id == claims.session_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.user_id == user.id,
            )
        )
    )
    if not live:
        raise Unauthorized("Session ended")
    rows = db.execute(
        select(Role.key, Role.is_platform, RolePermission.permission_key)
        .join(UserRole, UserRole.role_id == Role.id)
        .outerjoin(RolePermission, RolePermission.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    ).all()
    roles = frozenset(r[0] for r in rows)
    is_platform = any(r[1] for r in rows)
    if (claims.org_id is None) != is_platform:
        raise Unauthorized("Account unavailable")
    return Principal(
        user_id=user.id,
        org_id=user.organisation_id,
        email=user.email,
        full_name=user.full_name,
        roles=roles,
        permissions=frozenset(r[2] for r in rows if r[2]),
        session_id=claims.session_id,
        is_platform=is_platform,
        meta=meta,
    )


def current_principal(
    db: TenantDb,
    claims: Annotated[TokenClaims, Depends(get_claims)],
    meta: MetaDep,
) -> Principal:
    return build_principal(db, claims, meta)


PrincipalDep = Annotated[Principal, Depends(current_principal)]


def require(permission: str) -> Callable[..., Principal]:
    """Backend authorisation gate. Denials are audited in their own transaction."""

    def dependency(principal: PrincipalDep, sm: SessionMakerDep) -> Principal:
        if not principal.has(permission):
            audit_session = sm()
            try:
                set_tenant(audit_session, principal.org_id, platform=principal.org_id is None)
                record_audit(
                    audit_session,
                    principal.meta,
                    org_id=principal.org_id,
                    actor_user_id=principal.user_id,
                    action="ACCESS_DENIED",
                    resource_type="permission",
                    outcome="DENIED",
                    reason=permission,
                )
                audit_session.commit()
            finally:
                audit_session.close()
            raise Forbidden("You do not have permission to perform this action")
        return principal

    return dependency
