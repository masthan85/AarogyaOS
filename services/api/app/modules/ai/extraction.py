"""ClinicalExtractionTask: transcript segments in, reviewable candidates out.

Everything the model returns is untrusted. It is parsed strictly, each candidate must quote the
transcript exactly, and deterministic guardrails then decide what survives. The result is a queue
of candidates for a clinician; nothing here writes to the patient's record.
"""

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import guardrails
from app.ai.llm import LLMProvider, LLMRequest, LLMResponse, LLMUnavailable
from app.ai.prompts import EXTRACTION_VERSION, render_extraction
from app.ai.registry import get_llm
from app.ai.schemas import KINDS_BY_PURPOSE, ExtractionEnvelope
from app.core.config import Settings
from app.core.context import Principal
from app.core.errors import Conflict, TooManyRequests
from app.modules.ai.models import AiCandidate, AiExtraction, AiUsage
from app.modules.ai.schemas import AnalyseOut
from app.modules.audit.service import emit_event, record_audit
from app.modules.consent.queries import active_consent
from app.modules.interactions import service as interactions
from app.modules.interactions.models import (
    ClinicalInteraction,
    InteractionSpeaker,
    TranscriptSegment,
)
from app.modules.interactions.service import ConsentRequired
from app.modules.tenancy.policy import load_policy

MAX_NEW_SEGMENTS = 40
CONTEXT_SEGMENTS = 3
UNAVAILABLE = "AI assistance is unavailable right now. Carry on documenting manually."
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _org(principal: Principal) -> uuid.UUID:
    assert principal.org_id is not None
    return principal.org_id


def parse_json_object(text: str) -> dict[str, object]:
    """Strict: one JSON object, optionally wrapped in a code fence. Anything else is rejected."""
    value = json.loads(_FENCE.sub("", text.strip()))
    if not isinstance(value, dict):
        raise ValueError("not an object")
    return value


def call_llm(llm: LLMProvider, request: LLMRequest, timeout: float) -> LLMResponse:
    """Run the async provider from a worker thread, with a hard timeout."""
    return asyncio.run(asyncio.wait_for(llm.complete(request), timeout))


def record_usage(
    session: Session,
    principal: Principal,
    feature: str,
    llm: LLMProvider,
    resp: LLMResponse | None,
    status: str,
    ia: ClinicalInteraction | None,
    encounter_id: uuid.UUID | None,
    patient_id: uuid.UUID,
    latency_ms: int = 0,
) -> None:
    session.add(
        AiUsage(
            organisation_id=_org(principal),
            feature=feature,
            provider=llm.name,
            model=llm.model,
            patient_id=patient_id,
            encounter_id=encounter_id,
            interaction_id=ia.id if ia else None,
            user_id=principal.user_id,
            input_tokens=resp.input_tokens if resp else 0,
            output_tokens=resp.output_tokens if resp else 0,
            tokens_are_estimates=resp.token_counts_are_estimates if resp else False,
            latency_ms=resp.latency_ms if resp else latency_ms,
            status=status,
        )
    )


def analyse(
    session: Session, principal: Principal, settings: Settings, interaction_id: uuid.UUID
) -> AnalyseOut:
    org_id = _org(principal)
    ia = interactions.visible(session, principal, interaction_id)
    if not ia.ai_processing:
        raise Conflict("AI assistance was not switched on for this recording")
    policy = load_policy(session, org_id)
    if not policy.ai_processing_enabled:
        raise Conflict("AI processing is not enabled for this organisation")
    missing = [
        p
        for p in ("SPEECH_TRANSCRIPTION", "AI_PROCESSING")
        if active_consent(session, ia.patient_id, p) is None
    ]
    if missing:  # consent is re-checked on every run, not only when the recording started
        raise ConsentRequired(
            "The patient has not given the consent needed for AI assistance: " + ", ".join(missing),
            extra={"missing": missing},
        )

    recent = (
        session.scalar(
            select(func.count())
            .select_from(AiExtraction)
            .where(
                AiExtraction.interaction_id == ia.id,
                AiExtraction.created_at > datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        or 0
    )
    if recent >= settings.ai_analyses_per_minute:
        raise TooManyRequests("Analysis was run very recently. Wait a moment and try again.")

    last_done = (
        session.scalar(
            select(func.max(AiExtraction.to_seq)).where(
                AiExtraction.interaction_id == ia.id, AiExtraction.status == "OK"
            )
        )
        or 0
    )
    window = list(
        session.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.interaction_id == ia.id, TranscriptSegment.seq > last_done)
            .order_by(TranscriptSegment.seq)
            .limit(MAX_NEW_SEGMENTS)
        )
    )
    if not window:
        return AnalyseOut(status="NOTHING_NEW", is_development=False)
    context = list(
        session.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.interaction_id == ia.id, TranscriptSegment.seq <= last_done)
            .order_by(TranscriptSegment.seq.desc())
            .limit(CONTEXT_SEGMENTS)
        )
    )[::-1]

    roles = {
        s.speaker_id: s.role
        for s in session.scalars(
            select(InteractionSpeaker).where(InteractionSpeaker.interaction_id == ia.id)
        )
    }

    def role_of(seg: TranscriptSegment) -> str:
        return roles.get(seg.speaker_id or "", "UNKNOWN")

    allowed = sorted(KINDS_BY_PURPOSE.get(ia.purpose, frozenset()))
    payload = {
        "allowed_kinds": allowed,
        "segments": [
            {
                "seq": s.seq,
                "speaker_role": role_of(s),
                "language": s.language,
                "text": s.raw_text,
                "context_only": s in context,
            }
            for s in [*context, *window]
        ],
    }
    system, prompt = render_extraction(payload)
    request = LLMRequest("clinical_extraction", EXTRACTION_VERSION, system, prompt, payload)

    try:
        llm = get_llm(settings.llm_provider, environment=settings.environment)
    except LLMUnavailable:
        return AnalyseOut(status="FAILED", message=UNAVAILABLE)

    base = {
        "organisation_id": org_id,
        "interaction_id": ia.id,
        "patient_id": ia.patient_id,
        "encounter_id": ia.encounter_id,
        "triggered_by": principal.user_id,
        "prompt_version": EXTRACTION_VERSION,
        "provider": llm.name,
        "model": llm.model,
        "is_development": llm.is_development,
        "from_seq": window[0].seq,
        "to_seq": window[-1].seq,
    }

    def failed(code: str, usage_status: str, resp: LLMResponse | None) -> AnalyseOut:
        run = AiExtraction(**base, status="FAILED", error_code=code)
        session.add(run)
        record_usage(
            session,
            principal,
            "extraction",
            llm,
            resp,
            usage_status,
            ia,
            ia.encounter_id,
            ia.patient_id,
        )
        record_audit(
            session,
            principal.meta,
            org_id=org_id,
            actor_user_id=principal.user_id,
            action="AI_EXTRACTION_FAILED",
            resource_type="interaction",
            resource_id=ia.id,
            reason=code,
            ai_involved=True,
        )
        session.commit()
        return AnalyseOut(
            status="FAILED",
            extraction_id=run.id,
            message=UNAVAILABLE,
            is_development=llm.is_development,
        )

    try:
        resp = call_llm(llm, request, settings.llm_timeout_seconds)
    except TimeoutError:
        return failed("TIMEOUT", "TIMEOUT", None)
    except Exception:  # noqa: BLE001  (a vendor failure must never break the consultation)
        return failed("PROVIDER_ERROR", "ERROR", None)

    try:
        envelope = ExtractionEnvelope.model_validate(parse_json_object(resp.text))
    except (ValueError, ValidationError):
        return failed("INVALID_OUTPUT", "INVALID", resp)  # rejected whole: never repaired

    views = [guardrails.SegmentView(s.seq, s.raw_text, role_of(s), str(s.id)) for s in window]
    existing = set(
        session.scalars(select(AiCandidate.dedupe_key).where(AiCandidate.interaction_id == ia.id))
    )
    vetted = guardrails.vet_candidates(envelope.candidates, views, ia.purpose, existing)

    run = AiExtraction(
        **base,
        status="OK",
        proposed=len(envelope.candidates),
        kept=len(vetted.kept),
        dropped=vetted.dropped,
    )
    session.add(run)
    session.flush()
    for v in vetted.kept:
        c = v.candidate
        session.add(
            AiCandidate(
                organisation_id=org_id,
                extraction_id=run.id,
                interaction_id=ia.id,
                patient_id=ia.patient_id,
                encounter_id=ia.encounter_id,
                kind=c.kind,
                text=c.text.strip(),
                assertion=c.assertion,
                subject=c.subject,
                attributes=c.attributes,
                original_term=c.original_term,
                evidence=v.evidence,
                risk_flags=v.flags,
                dedupe_key=guardrails.dedupe_key(c.kind, c.text, c.assertion),
            )
        )
    record_usage(
        session, principal, "extraction", llm, resp, "OK", ia, ia.encounter_id, ia.patient_id
    )
    kinds = {v.candidate.kind for v in vetted.kept}
    event = (
        "ALLERGY_EXTRACTED"
        if "ALLERGY" in kinds
        else "SYMPTOM_EXTRACTED"
        if "SYMPTOM" in kinds
        else "AI_EXTRACTION_COMPLETED"
    )
    if vetted.kept:
        emit_event(
            session,
            org_id=org_id,
            event_type=event,
            aggregate_type="ai_extraction",
            aggregate_id=run.id,
            patient_id=ia.patient_id,
            encounter_id=ia.encounter_id,
            actor_user_id=principal.user_id,
            payload={"candidates": len(vetted.kept), "kinds": sorted(kinds)},
        )
    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action="AI_EXTRACTION_COMPLETED",
        resource_type="interaction",
        resource_id=ia.id,
        after={
            "proposed": len(envelope.candidates),
            "kept": len(vetted.kept),
            "dropped": vetted.dropped,
            "provider": llm.name,
        },
        ai_involved=True,
    )
    session.commit()
    return AnalyseOut(
        status="OK",
        extraction_id=run.id,
        new_candidates=len(vetted.kept),
        dropped=vetted.dropped,
        is_development=llm.is_development,
    )
