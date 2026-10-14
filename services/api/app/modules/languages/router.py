from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.core.context import Principal
from app.core.deps import PrincipalDep, TenantDb, require
from app.modules.languages import service
from app.modules.tenancy.policy import OrgPolicy, load_policy, save_policy

router = APIRouter(tags=["languages"])


class LanguageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tag: str
    name: str
    native_name: str
    script: str
    provider_support: dict[str, object]


@router.get("/languages", response_model=list[LanguageOut])
def list_languages(db: TenantDb, principal: PrincipalDep) -> list[LanguageOut]:
    """Languages this organisation can use. Driven by data, not code."""
    assert principal.org_id is not None
    policy = load_policy(db, principal.org_id)
    return [LanguageOut.model_validate(x) for x in service.available_languages(db, policy)]


@router.get("/organisations/current/policy", response_model=OrgPolicy)
def get_policy(
    db: TenantDb, principal: Annotated[Principal, Depends(require("org:read"))]
) -> OrgPolicy:
    assert principal.org_id is not None
    return load_policy(db, principal.org_id)


@router.put("/organisations/current/policy", response_model=OrgPolicy)
def put_policy(
    body: OrgPolicy, db: TenantDb, principal: Annotated[Principal, Depends(require("org:manage"))]
) -> OrgPolicy:
    return save_policy(db, principal, body)
