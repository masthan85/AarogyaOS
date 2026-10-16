import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.context import Principal
from app.core.deps import MetaDep, PrincipalDep, SettingsDep, SystemDb, TenantDb, require
from app.core.ratelimit import limiter_of
from app.modules.identity import service
from app.modules.identity.schemas import (
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RoleOut,
    TokenPair,
    UserCreate,
    UserOut,
    UserRolesUpdate,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(tags=["users"])


@auth_router.post("/login", response_model=TokenPair)
def login(
    body: LoginRequest, db: SystemDb, settings: SettingsDep, meta: MetaDep, request: Request
) -> TokenPair:
    limiter_of(request).check(
        f"login:{meta.ip_address}",
        limit=settings.login_attempts_per_minute_per_ip,
        window_seconds=60,
    )
    return service.login(
        db,
        settings,
        meta,
        organisation_slug=body.organisation_slug,
        email=body.email,
        password=body.password,
    )


@auth_router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, db: SystemDb, settings: SettingsDep, meta: MetaDep) -> TokenPair:
    return service.refresh(db, settings, meta, body.refresh_token)


@auth_router.post("/logout", status_code=204)
def logout(body: RefreshRequest, db: SystemDb, meta: MetaDep) -> Response:
    service.logout(db, meta, body.refresh_token)
    return Response(status_code=204)


@auth_router.get("/me", response_model=MeResponse)
def me(principal: PrincipalDep) -> MeResponse:
    return MeResponse(
        id=principal.user_id,
        organisation_id=principal.org_id,
        email=principal.email,
        full_name=principal.full_name,
        roles=sorted(principal.roles),
        permissions=sorted(principal.permissions),
    )


@users_router.get("/roles", response_model=list[RoleOut])
def roles(db: TenantDb, _: Annotated[Principal, Depends(require("role:read"))]) -> list[RoleOut]:
    return [RoleOut(key=r.key, name=r.name, permissions=p) for r, p in service.list_roles(db)]


@users_router.get("/users", response_model=list[UserOut])
def list_users(
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("user:read"))],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[UserOut]:
    return service.list_users(db, principal, limit, offset)


@users_router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate, db: TenantDb, principal: Annotated[Principal, Depends(require("user:manage"))]
) -> UserOut:
    return service.create_user(
        db,
        principal,
        email=body.email,
        full_name=body.full_name,
        password=body.password,
        role_keys=body.roles,
        preferred_language=body.preferred_language,
    )


@users_router.get("/users/{user_id}", response_model=UserOut)
def get_user(
    user_id: uuid.UUID, db: TenantDb, principal: Annotated[Principal, Depends(require("user:read"))]
) -> UserOut:
    return service.get_user(db, principal, user_id)


@users_router.put("/users/{user_id}/roles", response_model=UserOut)
def set_roles(
    user_id: uuid.UUID,
    body: UserRolesUpdate,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("user:manage"))],
) -> UserOut:
    return service.set_roles(db, principal, user_id, body.roles)


@users_router.post("/users/{user_id}/deactivate", response_model=UserOut)
def deactivate(
    user_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("user:manage"))],
) -> UserOut:
    return service.deactivate_user(db, principal, user_id)
