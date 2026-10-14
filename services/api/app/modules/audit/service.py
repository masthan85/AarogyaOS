import uuid

from sqlalchemy.orm import Session

from app.core.context import RequestMeta
from app.modules.audit.models import AuditLog, ClinicalEvent


def record_audit(
    session: Session,
    meta: RequestMeta,
    *,
    org_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None = None,
    outcome: str = "SUCCESS",
    reason: str | None = None,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
    ai_involved: bool = False,
) -> AuditLog:
    """Add an audit row to the caller's transaction. Never pass secrets or free-text PHI."""
    row = AuditLog(
        organisation_id=org_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        reason=reason,
        before=before,
        after=after,
        ai_involved=ai_involved,
        ip_address=meta.ip_address,
        user_agent=meta.user_agent,
        correlation_id=meta.correlation_id,
    )
    session.add(row)
    return row


def emit_event(
    session: Session,
    *,
    org_id: uuid.UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    encounter_id: uuid.UUID | None = None,
    payload: dict[str, object] | None = None,
) -> ClinicalEvent:
    """Write a domain event to the outbox in the same transaction as the change."""
    event = ClinicalEvent(
        organisation_id=org_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        actor_user_id=actor_user_id,
        patient_id=patient_id,
        encounter_id=encounter_id,
        payload=payload or {},
    )
    session.add(event)
    return event
