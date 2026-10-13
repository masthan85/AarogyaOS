"""Organisation-level recording, retention and language policy (stored in organisations.settings).

Defaults are the privacy-protective ones: nothing is recorded, nothing is sent to AI and audio is
discarded after transcription until an administrator decides otherwise.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import NotFound
from app.modules.audit.service import record_audit
from app.modules.tenancy.models import Organisation


class OrgPolicy(BaseModel):
    recording_enabled: bool = False
    ai_processing_enabled: bool = False
    audio_retention: Literal["DISCARD_AFTER_TRANSCRIPTION", "RETAIN_DAYS"] = (
        "DISCARD_AFTER_TRANSCRIPTION"
    )
    retain_days: int = Field(default=30, ge=1, le=3650)
    # Suggestions are a separate, optional layer on top of extraction.
    ai_suggestions_enabled: bool = False
    # When true, model suggestions without a cited, approved reference are dropped.
    ai_suggestions_require_source: bool = True
    # None = every language in the catalogue is available to this organisation.
    enabled_languages: list[str] | None = None
    # Patients younger than this need a guardian's consent. Confirm the right value with counsel.
    guardian_consent_under_age: int = Field(default=18, ge=0, le=21)

    @model_validator(mode="after")
    def _consistent(self) -> "OrgPolicy":
        if self.audio_retention == "RETAIN_DAYS" and not self.recording_enabled:
            raise ValueError("Audio cannot be retained when recording is disabled")
        if self.ai_suggestions_enabled and not self.ai_processing_enabled:
            raise ValueError("AI suggestions need AI processing to be enabled")
        return self


def load_policy(session: Session, org_id: uuid.UUID) -> OrgPolicy:
    org = session.get(Organisation, org_id)
    if org is None:
        raise NotFound("Organisation not found")
    return OrgPolicy.model_validate((org.settings or {}).get("policy", {}))


def save_policy(session: Session, principal: Principal, policy: OrgPolicy) -> OrgPolicy:
    assert principal.org_id is not None
    org = session.get(Organisation, principal.org_id)
    if org is None:
        raise NotFound("Organisation not found")
    before = OrgPolicy.model_validate((org.settings or {}).get("policy", {}))
    org.settings = {**(org.settings or {}), "policy": policy.model_dump()}
    changed = sorted(k for k, v in policy.model_dump().items() if v != getattr(before, k))
    record_audit(
        session,
        principal.meta,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        action="ORG_POLICY_UPDATED",
        resource_type="organisation",
        resource_id=org.id,
        before={k: getattr(before, k) for k in changed},
        after={k: getattr(policy, k) for k in changed},
    )
    session.commit()
    return policy
