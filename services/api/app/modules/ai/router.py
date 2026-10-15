import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select

from app.ai.knowledge import NotAvailable
from app.core.context import Principal
from app.core.deps import SettingsDep, TenantDb, require
from app.core.errors import Conflict, Forbidden
from app.modules.ai import chartqa, extraction, knowledge_service, review, suggestions
from app.modules.ai.models import AiUsage
from app.modules.ai.schemas import (
    AiUsageRow,
    AnalyseOut,
    AskIn,
    AskOut,
    CandidateOut,
    GenerateOut,
    KnowledgeDocIn,
    KnowledgeDocOut,
    ReviewBundle,
    ReviewIn,
    ReviewOut,
    SuggestionActionIn,
    SuggestionActionOut,
    SuggestionOut,
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
    suggestion_rows: list[SuggestionOut] = []
    if principal.has("ai:suggestions") and policy and policy.ai_suggestions_enabled:
        try:  # only the encounter's own doctor sees suggestions
            suggestion_rows = [
                suggestions.to_out(x)
                for x in suggestions.list_for_encounter(db, principal, encounter_id)
            ]
        except Forbidden:
            suggestion_rows = []
    return ReviewBundle(
        candidates=[
            review.to_out(c) for c in review.list_for_encounter(db, principal, encounter_id)
        ],
        suggestions=suggestion_rows,
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


@router.post("/encounters/{encounter_id}/ai/suggestions", response_model=GenerateOut)
def generate_suggestions(
    encounter_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("ai:suggestions"))],
    settings: SettingsDep,
) -> GenerateOut:
    return suggestions.generate(db, principal, settings, encounter_id)


@router.get("/encounters/{encounter_id}/ai/suggestions", response_model=list[SuggestionOut])
def list_suggestions(
    encounter_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("ai:suggestions"))],
) -> list[SuggestionOut]:
    return [
        suggestions.to_out(s) for s in suggestions.list_for_encounter(db, principal, encounter_id)
    ]


@router.post("/ai/suggestions/{suggestion_id}/action", response_model=SuggestionActionOut)
def act_on_suggestion(
    suggestion_id: uuid.UUID,
    body: SuggestionActionIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("ai:suggestions"))],
) -> SuggestionActionOut:
    return suggestions.act(
        db, principal, suggestion_id, body.action, body.title, body.explanation, body.reason
    )


# ---- reference knowledge --------------------------------------------------------------


@router.get("/knowledge/documents", response_model=list[KnowledgeDocOut])
def list_documents(
    db: TenantDb, _: Annotated[Principal, Depends(require("knowledge:read"))]
) -> list[KnowledgeDocOut]:
    return knowledge_service.list_documents(db)


@router.post("/knowledge/documents", response_model=KnowledgeDocOut, status_code=201)
def add_document(
    body: KnowledgeDocIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("knowledge:manage"))],
    settings: SettingsDep,
) -> KnowledgeDocOut:
    try:
        embedder = knowledge_service.get_embedder(
            settings.embedding_provider, environment=settings.environment
        )
    except NotAvailable as exc:
        raise Conflict(str(exc)) from exc
    return knowledge_service.create_document(db, principal, embedder, body)


@router.post("/knowledge/documents/{doc_id}/approve", response_model=KnowledgeDocOut)
def approve_document(
    doc_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("knowledge:manage"))],
) -> KnowledgeDocOut:
    return knowledge_service.approve(db, principal, doc_id)


@router.post("/knowledge/documents/{doc_id}/retire", response_model=KnowledgeDocOut)
def retire_document(
    doc_id: uuid.UUID,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("knowledge:manage"))],
) -> KnowledgeDocOut:
    return knowledge_service.retire(db, principal, doc_id)


@router.get("/usage/ai", response_model=list[AiUsageRow])
def ai_usage(
    db: TenantDb, _: Annotated[Principal, Depends(require("usage:read"))]
) -> list[AiUsageRow]:
    ok = func.sum(case((AiUsage.status == "OK", 1), else_=0))
    rows = db.execute(
        select(
            AiUsage.feature,
            AiUsage.provider,
            AiUsage.model,
            func.count(),
            ok,
            func.sum(AiUsage.input_tokens),
            func.sum(AiUsage.output_tokens),
            func.bool_or(AiUsage.tokens_are_estimates),
            func.avg(AiUsage.latency_ms),
            func.sum(AiUsage.estimated_cost_paise),
        ).group_by(AiUsage.feature, AiUsage.provider, AiUsage.model)
    ).all()
    return [
        AiUsageRow(
            feature=r[0],
            provider=r[1],
            model=r[2],
            calls=r[3],
            ok=int(r[4] or 0),
            failed=r[3] - int(r[4] or 0),
            input_tokens=int(r[5] or 0),
            output_tokens=int(r[6] or 0),
            tokens_are_estimates=bool(r[7]),
            avg_latency_ms=float(r[8]) if r[8] is not None else None,
            estimated_cost_paise=int(r[9]) if r[9] is not None else None,
        )
        for r in rows
    ]


@router.post("/patients/{patient_id}/ai/ask", response_model=AskOut)
def ask_chart(
    patient_id: uuid.UUID,
    body: AskIn,
    db: TenantDb,
    principal: Annotated[Principal, Depends(require("ai:suggestions"))],
    _chart: Annotated[Principal, Depends(require("patient:clinical"))],
    settings: SettingsDep,
) -> AskOut:
    return chartqa.ask(db, principal, settings, patient_id, body.question)
