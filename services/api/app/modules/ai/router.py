import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.context import Principal
from app.core.deps import SettingsDep, TenantDb, require
from app.modules.ai import extraction, review
from app.modules.ai.schemas import (
    AnalyseOut,
    CandidateOut,
    ReviewBundle,
    ReviewIn,
    ReviewOut,
)
from app.modules.tenancy.policy import load_policy

router = APIRouter(tags=["clinical-ai"])


@router.post("/interactions/{interaction_id}/ai/analyse", response_model=AnalyseOut)
def analyse(
    interaction_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("ai:analyse"))],
    settings: SettingsDep,
) -> AnalyseOut:
    return extraction.analyse(db, principal, settings, interaction_id)


@router.get("/interactions/{interaction_id}/ai/candidates", response_model=list[CandidateOut])
def interaction_candidates(
    interaction_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("ai:review"))],
) -> list[CandidateOut]:
    return [review.to_out(c) for c in review.list_for_interaction(db, principal, interaction_id)]


@router.get("/encounters/{encounter_id}/ai/review", response_model=ReviewBundle)
def encounter_review(
    encounter_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("ai:review"))],
) -> ReviewBundle:
    policy = load_policy(db, principal.org_id) if principal.org_id else None
    return ReviewBundle(
        candidates=[
            review.to_out(c) for c in review.list_for_encounter(db, principal, encounter_id)
        ],
        suggestions=[],
        ai_enabled=bool(policy and policy.ai_processing_enabled),
        suggestions_enabled=bool(policy and policy.ai_suggestions_enabled),
    )


@router.post("/ai/candidates/{candidate_id}/review", response_model=ReviewOut)
def review_candidate(
    candidate_id: uuid.UUID,
    body: ReviewIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("ai:review"))],
) -> ReviewOut:
    return review.review(
        db, principal, candidate_id, body.action, body.edited_text, body.note, body.mode
    )
