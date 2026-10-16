import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.context import Principal
from app.core.deps import TenantDb, require
from app.modules.cover import service
from app.modules.cover.service import Colleague, CoverIn, CoverOut

router = APIRouter(tags=["cover"])
Reviewer = Annotated[Principal, Depends(require("result:review"))]


@router.get("/cover/colleagues", response_model=list[Colleague])
def colleagues(db: TenantDb, principal: Reviewer) -> list[Colleague]:
    return service.colleagues(db, principal)


@router.get("/cover", response_model=list[CoverOut])
def mine(db: TenantDb, principal: Reviewer) -> list[CoverOut]:
    return service.mine(db, principal)


@router.post("/cover", response_model=CoverOut, status_code=201)
def create(body: CoverIn, db: TenantDb, principal: Reviewer) -> CoverOut:
    return service.create(db, principal, body)


@router.post("/cover/{cover_id}/end", response_model=CoverOut)
def end(cover_id: uuid.UUID, db: TenantDb, principal: Reviewer) -> CoverOut:
    return service.revoke(db, principal, cover_id)
