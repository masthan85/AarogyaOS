import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    organisation_slug: str | None = Field(default=None, max_length=60)
    email: EmailStr
    password: str = Field(max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(max_length=200)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class MeResponse(BaseModel):
    id: uuid.UUID
    organisation_id: uuid.UUID | None
    email: str
    full_name: str
    roles: list[str]
    permissions: list[str]


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=200)
    roles: list[str] = Field(min_length=1)
    preferred_language: str = Field(default="en-IN", max_length=35)


class UserRolesUpdate(BaseModel):
    roles: list[str] = Field(min_length=1)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    preferred_language: str
    mfa_enabled: bool
    last_login_at: datetime | None
    roles: list[str] = []


class RoleOut(BaseModel):
    key: str
    name: str
    permissions: list[str]
