import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

SLUG = r"^[a-z0-9](?:[a-z0-9-]{1,58}[a-z0-9])$"


class OrganisationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=SLUG)
    admin_email: EmailStr
    admin_full_name: str = Field(min_length=1, max_length=200)
    admin_password: str = Field(min_length=12, max_length=200)


class OrganisationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: str


class FacilityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    kind: str = Field(default="CLINIC", pattern=r"^(CLINIC|HOSPITAL|BRANCH)$")
    address: str | None = Field(default=None, max_length=500)
    timezone: str = Field(default="Asia/Kolkata", max_length=50)


class FacilityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, pattern=r"^(ACTIVE|INACTIVE)$")


class FacilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    kind: str
    address: str | None
    timezone: str
    status: str


class DepartmentCreate(BaseModel):
    facility_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    specialty: str | None = Field(default=None, max_length=100)


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    facility_id: uuid.UUID
    name: str
    specialty: str | None
    status: str
