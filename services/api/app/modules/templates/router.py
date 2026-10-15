import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.context import Principal
from app.core.deps import TenantDb, require
from app.modules.templates import service
from app.modules.templates.service import TemplateIn, TemplateOut

router = APIRouter(tags=["note-templates"])


@router.get("/note-templates", response_model=list[TemplateOut])
def list_templates(
    db: TenantDb, principal: Annotated[Principal, Depends(require("note:clinical"))]
) -> list[TemplateOut]:
    return service.list_templates(db)


@router.get("/note-templates/all", response_model=list[TemplateOut])
def list_all_templates(
    db: TenantDb, principal: Annotated[Principal, Depends(require("org:manage"))]
) -> list[TemplateOut]:
    return service.list_templates(db, include_inactive=True)


@router.post("/note-templates", response_model=TemplateOut, status_code=201)
def create_template(
    body: TemplateIn, db: TenantDb, principal: Annotated[Principal, Depends(require("org:manage"))]
) -> TemplateOut:
    return service.create(db, principal, body)


@router.put("/note-templates/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: uuid.UUID,
    body: TemplateIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("org:manage"))],
) -> TemplateOut:
    return service.update(db, principal, template_id, body)
