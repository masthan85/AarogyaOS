"""Decision support for the treating doctor: things to consider, never things done.

Two sources, kept visibly apart:
* DETERMINISTIC - plain rules over the patient's own record (missing allergy status, abnormal
  results, a discussed treatment that clashes with a recorded allergy). Always available.
* MODEL - proposals from the language model, built only from the record and from *approved*
  reference passages, then vetted: unknown references, uncited clinical advice and anything that
  claims an action are dropped. Safety categories (allergy, interaction, contraindication) are
  never taken from the model.

A suggestion changes nothing in the record. Accepting an investigation suggestion creates a DRAFT
order the doctor still has to place; every other acceptance is an acknowledgement.
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import guardrails
from app.ai.knowledge import KnowledgeHit, NotAvailable
from app.ai.llm import LLMRequest, LLMUnavailable
from app.ai.prompts import SUGGESTION_VERSION, render_suggestions
from app.ai.registry import get_llm
from app.ai.schemas import SuggestionEnvelope, SuggestionItem
from app.core.config import Settings
from app.core.context import Principal
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.modules.ai import knowledge_service
from app.modules.ai.extraction import UNAVAILABLE, call_llm, parse_json_object, record_usage
from app.modules.ai.models import AiCandidate, AiSuggestion, AiSuggestionAction
from app.modules.ai.schemas import GenerateOut, SuggestionActionOut, SuggestionOut
from app.modules.audit.service import emit_event, record_audit
from app.modules.clinical.encounters import get_encounter, open_encounter, require_owner
from app.modules.clinical.models import (
    Allergy,
    ClinicalNote,
    Condition,
    Encounter,
    InvestigationResult,
    Observation,
    PatientMedication,
    ServiceRequest,
)
from app.modules.consent.queries import active_consent
from app.modules.tenancy.policy import load_policy

SAFETY_CATEGORIES = frozenset({"ALLERGY_WARNING", "INTERACTION", "CONTRAINDICATION"})
MODEL_CATEGORIES = [
    "IMPORTANT_INFORMATION",
    "MISSING_HISTORY_QUESTION",
    "DIFFERENTIAL",
    "INVESTIGATION",
    "MEDICATION_CONSIDERATION",
    "PREVIOUS_INFORMATION",
    "ABNORMAL_RESULT",
    "GUIDELINE",
    "REFERRAL",
    "FOLLOW_UP",
    "PATIENT_EDUCATION",
]
# Advice that must rest on an approved reference. The others only point at the patient's own data.
NEEDS_SOURCE = frozenset(
    {
        "DIFFERENTIAL",
        "INVESTIGATION",
        "MEDICATION_CONSIDERATION",
        "GUIDELINE",
        "REFERRAL",
        "FOLLOW_UP",
        "PATIENT_EDUCATION",
    }
)
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def _org(principal: Principal) -> uuid.UUID:
    assert principal.org_id is not None
    return principal.org_id


def _key(category: str, title: str) -> str:
    return f"{category}|{' '.join(_TOKEN.findall(title.casefold()))}"[:400]


def to_out(s: AiSuggestion) -> SuggestionOut:
    return SuggestionOut.model_validate(s)


def _mentions(text: str, term: str) -> bool:
    t = " ".join(_TOKEN.findall(term.casefold()))
    return len(t) >= 3 and t in " ".join(_TOKEN.findall(text.casefold()))


class _Context:
    """What the record says about this encounter, with a stable ref for each item."""

    def __init__(self, session: Session, enc: Encounter) -> None:
        pid = enc.patient_id

        def current(model: Any) -> Any:
            return (
                model.patient_id == pid,
                model.is_current.is_(True),
                model.verification_state != "CLINICIAN_REJECTED",
            )

        self.allergies = list(session.scalars(select(Allergy).where(*current(Allergy))))
        self.medications = list(
            session.scalars(
                select(PatientMedication).where(
                    *current(PatientMedication), PatientMedication.status == "ACTIVE"
                )
            )
        )
        self.conditions = list(session.scalars(select(Condition).where(*current(Condition))))
        self.notes = list(
            session.scalars(
                select(ClinicalNote).where(
                    *current(ClinicalNote), ClinicalNote.encounter_id == enc.id
                )
            )
        )
        self.observations = list(
            session.scalars(
                select(Observation).where(*current(Observation), Observation.encounter_id == enc.id)
            )
        )
        self.results = list(
            session.scalars(
                select(InvestigationResult).where(
                    InvestigationResult.patient_id == pid,
                    InvestigationResult.interpretation.in_(
                        ["HIGH", "LOW", "CRITICAL_HIGH", "CRITICAL_LOW", "ABNORMAL"]
                    ),
                )
            )
        )
        self.pending = list(
            session.scalars(
                select(AiCandidate).where(
                    AiCandidate.encounter_id == enc.id, AiCandidate.status == "PENDING"
                )
            )
        )

    @property
    def allergy_status_known(self) -> bool:
        return bool(self.allergies)

    def payload(self) -> tuple[dict[str, Any], set[str]]:
        refs: dict[str, Any] = {
            "allergies": [
                {"ref": f"allergy:{a.id}", "substance": a.substance, "nka": a.is_nka}
                for a in self.allergies
            ],
            "medicines": [{"ref": f"med:{m.id}", "name": m.name} for m in self.medications],
            "conditions": [
                {"ref": f"cond:{c.id}", "display": c.display, "certainty": c.certainty}
                for c in self.conditions
            ],
            "notes": [
                {"ref": f"note:{n.id}", "type": n.note_type, "text": n.content[:400]}
                for n in self.notes
            ],
            "observations": [
                {
                    "ref": f"obs:{o.id}",
                    "code": o.code,
                    "value": str(o.value),
                    "unit": o.unit,
                    "interpretation": o.interpretation,
                }
                for o in self.observations
            ],
            "abnormal_results": [
                {"ref": f"res:{r.id}", "name": r.test_name, "interpretation": r.interpretation}
                for r in self.results
            ],
            "unreviewed_ai_items": [
                {"ref": f"cand:{c.id}", "kind": c.kind, "text": c.text, "assertion": c.assertion}
                for c in self.pending
            ],
        }
        ids = {item["ref"] for group in refs.values() for item in group}
        return refs, ids

    def query_text(self) -> str:
        parts = [n.content for n in self.notes] + [c.display for c in self.conditions]
        parts += [c.text for c in self.pending if c.kind in ("SYMPTOM", "CHIEF_COMPLAINT")]
        return " ".join(parts)[:1000]


def _deterministic(ctx: _Context) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def add(category: str, title: str, explanation: str, **extra: Any) -> None:
        out.append(
            {
                "category": category,
                "title": title,
                "explanation": explanation,
                "uncertainty": "LOW",
                "supporting_context": extra.pop("supporting_context", []),
                "warnings": extra.pop("warnings", []),
                "payload": extra.pop("payload", {}),
            }
        )

    if not ctx.allergy_status_known:
        add(
            "IMPORTANT_INFORMATION",
            "Allergy status is not recorded",
            "Nothing is recorded about allergies for this patient, not even 'no known allergies'. "
            "Ask before prescribing.",
        )
    if not ctx.medications:
        add(
            "MISSING_HISTORY_QUESTION",
            "Current medicines are not recorded",
            "No current medicines are on record. Ask what the patient is taking, including "
            "over-the-counter and traditional medicines.",
        )
    if not any(n.note_type == "CHIEF_COMPLAINT" for n in ctx.notes):
        add(
            "MISSING_HISTORY_QUESTION",
            "No chief complaint recorded for this visit",
            "The reason for the visit has not been recorded yet.",
        )
    for o in ctx.observations:
        if o.interpretation in ("HIGH", "LOW", "CRITICAL_HIGH", "CRITICAL_LOW"):
            flag = o.interpretation.replace("_", " ").lower()
            add(
                "ABNORMAL_RESULT",
                f"{o.code.replace('_', ' ').title()} is {flag}",
                f"Recorded value {o.value} {o.unit} was flagged {flag} against the reference "
                "ranges in use.",
                supporting_context=[{"ref": f"obs:{o.id}", "label": o.code}],
            )
    for r in ctx.results:
        add(
            "ABNORMAL_RESULT",
            f"Result flagged {r.interpretation.replace('_', ' ').lower()}: {r.test_name}",
            "A result on this patient's record was flagged outside its reference range.",
            supporting_context=[{"ref": f"res:{r.id}", "label": r.test_name}],
        )
    # Treatments or medicines mentioned in the conversation that clash with a recorded allergy.
    for cand in ctx.pending:
        if cand.kind not in ("TREATMENT_DISCUSSED", "MEDICATION") or cand.assertion == "ABSENT":
            continue
        for a in ctx.allergies:
            if a.is_nka or a.certainty == "HISTORICAL":
                continue
            if _mentions(cand.text, a.substance) or _mentions(a.substance, cand.text):
                add(
                    "ALLERGY_WARNING",
                    f"'{cand.text}' was discussed but the patient is recorded as allergic to "
                    f"{a.substance}",
                    "Check this before anything is prescribed. This is a name match against the "
                    "recorded allergy, not a check of drug families.",
                    supporting_context=[
                        {"ref": f"allergy:{a.id}", "label": a.substance},
                        {"ref": f"cand:{cand.id}", "label": cand.text},
                    ],
                    warnings=["Name match only; related drug classes are not checked here."],
                )
    return out


def _vet_model_items(
    raw: list[dict[str, Any]],
    refs: set[str],
    hits: dict[str, KnowledgeHit],
    ctx: _Context,
    require_source: bool,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    dropped: dict[str, int] = {}

    def drop(why: str) -> None:
        dropped[why] = dropped.get(why, 0) + 1

    kept: list[dict[str, Any]] = []
    for r in raw:
        try:
            item = SuggestionItem.model_validate(r)
        except ValidationError:
            drop("invalid")
            continue
        category = item.category
        if category in SAFETY_CATEGORIES:
            drop("safety_category_from_model")
            continue
        if category not in MODEL_CATEGORIES:
            drop("category_not_allowed")
            continue
        if guardrails.claims_autonomous_action(f"{item.title}. {item.explanation}"):
            drop("claims_action")
            continue
        if any(ref not in refs for ref in item.supporting_refs):
            drop("unknown_reference")
            continue
        if any(cid not in hits for cid in item.source_chunk_ids):
            drop("unknown_source")
            continue
        if category in NEEDS_SOURCE and require_source and not item.source_chunk_ids:
            drop("no_source")
            continue
        warnings: list[str] = []
        medicine = item.medicine_name or ""
        if medicine:
            conflict = next(
                (a for a in ctx.allergies if not a.is_nka and _mentions(medicine, a.substance)),
                None,
            )
            if conflict:  # a model suggestion that touches a recorded allergy becomes a warning
                category = "ALLERGY_WARNING"
                warnings.append(f"Recorded allergy: {conflict.substance}")
            elif any(
                _mentions(medicine, m.name) or _mentions(m.name, medicine) for m in ctx.medications
            ):
                warnings.append("The patient is already recorded as taking this medicine")
        payload: dict[str, str] = {}
        if item.test_name:
            payload["test"] = item.test_name
            payload["category"] = item.test_category or "OTHER"
        if medicine:
            payload["medicine"] = medicine
        kept.append(
            {
                "category": category,
                "title": item.title,
                "explanation": item.explanation,
                "uncertainty": item.uncertainty,
                "uncertainty_note": item.uncertainty_note,
                "supporting_context": [{"ref": ref, "label": ref} for ref in item.supporting_refs],
                "evidence_sources": [
                    {
                        "chunk_id": cid,
                        "document": hits[cid].title,
                        "publisher": hits[cid].publisher,
                        "version": hits[cid].version,
                        "excerpt": hits[cid].text[:400],
                    }
                    for cid in item.source_chunk_ids
                ],
                "warnings": warnings,
                "payload": payload,
            }
        )
    return kept, dropped


def generate(
    session: Session, principal: Principal, settings: Settings, encounter_id: uuid.UUID
) -> GenerateOut:
    org_id = _org(principal)
    enc = open_encounter(session, encounter_id)
    require_owner(session, principal, enc)
    policy = load_policy(session, org_id)
    if not policy.ai_suggestions_enabled:
        raise Conflict("AI suggestions are not enabled for this organisation")

    existing = set(
        session.scalars(select(AiSuggestion.dedupe_key).where(AiSuggestion.encounter_id == enc.id))
    )
    ctx = _Context(session, enc)
    created = 0
    dropped: dict[str, int] = {}

    def store(item: dict[str, Any], origin: str, llm: Any = None) -> None:
        nonlocal created
        key = _key(item["category"], item["title"])
        if key in existing:
            dropped["duplicate"] = dropped.get("duplicate", 0) + 1
            return
        existing.add(key)
        row = AiSuggestion(
            organisation_id=org_id,
            patient_id=enc.patient_id,
            encounter_id=enc.id,
            category=item["category"],
            title=item["title"][:160],
            explanation=item["explanation"][:800],
            uncertainty=item.get("uncertainty", "MEDIUM"),
            uncertainty_note=item.get("uncertainty_note"),
            supporting_context=item.get("supporting_context", []),
            evidence_sources=item.get("evidence_sources", []),
            payload=item.get("payload", {}),
            warnings=item.get("warnings", []),
            origin=origin,
            provider=llm.name if llm else None,
            model=llm.model if llm else None,
            prompt_version=SUGGESTION_VERSION if llm else None,
            dedupe_key=key,
        )
        session.add(row)
        session.flush()
        created += 1
        emit_event(
            session,
            org_id=org_id,
            event_type="AI_SUGGESTION_CREATED",
            aggregate_type="ai_suggestion",
            aggregate_id=row.id,
            patient_id=enc.patient_id,
            encounter_id=enc.id,
            actor_user_id=principal.user_id,
            payload={"category": row.category, "origin": origin},
        )

    for item in _deterministic(ctx):
        store(item, "DETERMINISTIC")

    model_used = False
    message: str | None = None
    if policy.ai_processing_enabled and active_consent(session, enc.patient_id, "AI_PROCESSING"):
        model_used, message = _model_pass(
            session,
            principal,
            settings,
            enc,
            ctx,
            policy.ai_suggestions_require_source,
            store,
            dropped,
        )
    elif policy.ai_processing_enabled:
        message = "Model suggestions need the patient's AI-processing consent."

    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action="AI_SUGGESTIONS_GENERATED",
        resource_type="encounter",
        resource_id=enc.id,
        after={"created": created, "model_used": model_used},
        ai_involved=model_used,
    )
    session.commit()
    return GenerateOut(created=created, dropped=dropped, model_used=model_used, message=message)


def _model_pass(
    session: Session,
    principal: Principal,
    settings: Settings,
    enc: Encounter,
    ctx: _Context,
    require_source: bool,
    store: Any,
    dropped: dict[str, int],
) -> tuple[bool, str | None]:
    try:
        llm = get_llm(settings.llm_provider, environment=settings.environment)
        embedder = knowledge_service.get_embedder(
            settings.embedding_provider, environment=settings.environment
        )
    except (LLMUnavailable, NotAvailable):
        return False, UNAVAILABLE
    hits = {h.chunk_id: h for h in knowledge_service.retrieve(session, embedder, ctx.query_text())}
    context, refs = ctx.payload()
    payload = {
        "allowed_categories": MODEL_CATEGORIES,
        "context": context,
        "knowledge": [
            {"chunk_id": h.chunk_id, "title": h.title, "publisher": h.publisher, "text": h.text}
            for h in hits.values()
        ],
    }
    system, prompt = render_suggestions(payload)
    request = LLMRequest("suggestions", SUGGESTION_VERSION, system, prompt, payload)
    try:
        resp = call_llm(llm, request, settings.llm_timeout_seconds)
    except TimeoutError:
        record_usage(
            session, principal, "suggestions", llm, None, "TIMEOUT", None, enc.id, enc.patient_id
        )
        return False, UNAVAILABLE
    except Exception:  # noqa: BLE001  (a vendor failure must never block the consultation)
        record_usage(
            session, principal, "suggestions", llm, None, "ERROR", None, enc.id, enc.patient_id
        )
        return False, UNAVAILABLE
    try:
        envelope = SuggestionEnvelope.model_validate(parse_json_object(resp.text))
    except (ValueError, ValidationError):
        record_usage(
            session, principal, "suggestions", llm, resp, "INVALID", None, enc.id, enc.patient_id
        )
        return False, UNAVAILABLE
    record_usage(session, principal, "suggestions", llm, resp, "OK", None, enc.id, enc.patient_id)
    kept, why = _vet_model_items(envelope.suggestions, refs, hits, ctx, require_source)
    for k, n in why.items():
        dropped[k] = dropped.get(k, 0) + n
    for item in kept:
        store(item, "MODEL", llm)
    return True, None


def list_for_encounter(
    session: Session, principal: Principal, encounter_id: uuid.UUID
) -> list[AiSuggestion]:
    enc = get_encounter(session, encounter_id)
    require_owner(session, principal, enc)
    return list(
        session.scalars(
            select(AiSuggestion)
            .where(AiSuggestion.encounter_id == enc.id)
            .order_by(AiSuggestion.created_at, AiSuggestion.id)
        )
    )


def act(
    session: Session,
    principal: Principal,
    suggestion_id: uuid.UUID,
    action: str,
    title: str | None,
    explanation: str | None,
    reason: str | None,
) -> SuggestionActionOut:
    org_id = _org(principal)
    s = session.get(AiSuggestion, suggestion_id)
    if s is None:
        raise NotFound("Suggestion not found")
    enc = get_encounter(session, s.encounter_id)
    require_owner(session, principal, enc)
    if s.status != "PENDING":
        raise Conflict("This suggestion has already been dealt with")
    previous = {"title": s.title, "explanation": s.explanation}
    new: dict[str, str] | None = None
    result_kind: str | None = None
    result_id: uuid.UUID | None = None

    if action == "edit":
        if not (title or explanation):
            raise AppError("Enter the corrected wording")
        s.title = (title or s.title).strip()
        s.explanation = (explanation or s.explanation).strip()
        new = {"title": s.title, "explanation": s.explanation}
    if action in ("accept", "edit"):
        open_encounter(session, enc.id)
        if s.category == "INVESTIGATION" and s.payload.get("test"):
            if not principal.has("order:write"):
                raise Forbidden("Only a doctor can draft an investigation")
            order = ServiceRequest(
                organisation_id=org_id,
                patient_id=s.patient_id,
                encounter_id=enc.id,
                category=s.payload.get("category", "OTHER"),
                name=s.payload["test"][:200],
                reason=f"Suggested for consideration: {s.title}"[:500],
                status="DRAFT",  # a DRAFT: the doctor still has to place it
                source="AI_EXTRACTED",
                created_by=principal.user_id,
            )
            session.add(order)
            session.flush()
            result_kind, result_id = "service_requests", order.id
        s.status = "EDITED" if action == "edit" else "ACCEPTED"
    elif action == "reject":
        s.status = "REJECTED"
    else:
        s.status = "DISMISSED"
    s.acted_by, s.acted_at = principal.user_id, datetime.now(UTC)

    session.add(
        AiSuggestionAction(
            organisation_id=org_id,
            suggestion_id=s.id,
            action=action.upper(),
            actor_user_id=principal.user_id,
            previous=previous if action == "edit" else None,
            new=new,
            reason=reason,
            result_kind=result_kind,
            result_id=result_id,
        )
    )
    event = {
        "accept": "AI_SUGGESTION_ACCEPTED",
        "edit": "AI_SUGGESTION_EDITED",
        "reject": "AI_SUGGESTION_REJECTED",
        "dismiss": "AI_SUGGESTION_DISMISSED",
    }[action]
    emit_event(
        session,
        org_id=org_id,
        event_type=event,
        aggregate_type="ai_suggestion",
        aggregate_id=s.id,
        patient_id=s.patient_id,
        encounter_id=enc.id,
        actor_user_id=principal.user_id,
        payload={"category": s.category, "origin": s.origin},
    )
    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action=event,
        resource_type="ai_suggestion",
        resource_id=s.id,
        after={"category": s.category, "became": result_kind},
        ai_involved=s.origin == "MODEL",
    )
    session.commit()
    return SuggestionActionOut(suggestion=to_out(s), result_kind=result_kind, result_id=result_id)
