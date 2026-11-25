import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.core.context import Principal
from app.core.deps import TenantDb, require
from app.core.pagination import newest_first
from app.modules.audit.models import AuditLog

router = APIRouter(tags=["audit"])


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: uuid.UUID | None
    outcome: str
    reason: str | None
    before: dict[str, object] | None
    after: dict[str, object] | None
    ai_involved: bool
    correlation_id: str | None


@router.get("/audit-logs", response_model=list[AuditLogOut])
def list_audit_logs(
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("audit:read"))],
    action: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    before: Annotated[
        uuid.UUID | None, Query(description="Id of the last entry already received")
    ] = None,
) -> list[AuditLogOut]:
    stmt = select(AuditLog).where(AuditLog.organisation_id == principal.org_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    stmt = newest_first(db, stmt, AuditLog, AuditLog.occurred_at, before)
    rows = db.scalars(stmt.limit(limit).offset(offset))
    return [AuditLogOut.model_validate(r) for r in rows]
