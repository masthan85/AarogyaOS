"""Ask a question about one patient's chart; get an answer that cites the entries it rests on.

Only entries a clinician has not rejected and that are the current version are searched. Unreviewed
AI candidates and suggestions are NOT part of the chart. The answer comes from the model but is
vetted: a statement without a valid citation is dropped, and if nothing survives the answer is
"not found in the record", never a guess. A plain keyword search over the same entries is always
returned alongside, so the feature still helps when AI is off, unconsented or unavailable.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import guardrails
from app.ai.llm import LLMRequest, LLMUnavailable
from app.ai.prompts import CHART_QA_VERSION, render_chart_qa
from app.ai.registry import get_llm
from app.core.config import Settings
from app.core.context import Principal
from app.core.errors import NotFound, TooManyRequests
from app.modules.ai.extraction import UNAVAILABLE, call_llm, parse_json_object, record_usage
from app.modules.ai.models import AiUsage
from app.modules.ai.schemas import AskOut, CitationOut, MatchOut, StatementOut
from app.modules.audit.service import record_audit
from app.modules.clinical.models import (
    Allergy,
    ClinicalNote,
    Condition,
    FollowUp,
    InvestigationResult,
    Observation,
    PatientMedication,
    Prescription,
    PrescriptionItem,
    ServiceRequest,
)
from app.modules.consent.queries import active_consent
from app.modules.patients.models import Patient
from app.modules.tenancy.policy import load_policy

MAX_ITEMS_PER_KIND = 40
MAX_STATEMENTS = 8
_WORD = re.compile(r"[^\W_]{3,}", re.UNICODE)
_STOP = frozenset(
    "the and for was were what when which who how did does has have had with this that from "
    "about patient last any are there their his her she him they them into been being".split()
)


class _Stmt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=500)
    refs: list[str] = Field(min_length=1, max_length=6)


class _Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statements: list[dict[str, Any]] = Field(max_length=30)


def _day(dt: datetime | None) -> str | None:
    return dt.date().isoformat() if dt else None


def build_items(session: Session, patient_id: uuid.UUID) -> list[dict[str, Any]]:
    """The chart as a flat list of citable entries: {ref, text, date}."""
    out: list[dict[str, Any]] = []

    def facts(model: Any, *where: Any, order: Any = None) -> list[Any]:
        q = select(model).where(
            model.patient_id == patient_id,
            model.is_current.is_(True),
            model.verification_state != "CLINICIAN_REJECTED",
            *where,
        )
        if order is not None:
            q = q.order_by(order).limit(MAX_ITEMS_PER_KIND)
        return list(session.scalars(q))

    def add(prefix: str, row: Any, text: str, when: datetime | None) -> None:
        out.append({"ref": f"{prefix}:{row.id}", "text": text, "date": _day(when)})

    for c in facts(Condition):
        add(
            "cond",
            c,
            f"Diagnosis or problem: {c.display} "
            f"({c.certainty.lower()}, {c.clinical_status.lower()})",
            c.recorded_at,
        )
    for a in facts(Allergy):
        text = (
            "No known allergies recorded"
            if a.is_nka
            else f"Allergy: {a.substance} ({a.certainty.lower()}"
            + (f", reaction {a.reaction}" if a.reaction else "")
            + ")"
        )
        add("allergy", a, text, a.recorded_at)
    for m in facts(PatientMedication):
        parts = " ".join(x for x in (m.name, m.dose, m.route, m.frequency) if x)
        add("med", m, f"Medicine ({m.status.lower()}): {parts}", m.recorded_at)
    for o in facts(Observation, order=Observation.observed_at.desc()):
        flag = (
            ""
            if o.interpretation in ("UNKNOWN", "NORMAL")
            else f", {o.interpretation.replace('_', ' ').lower()}"
        )
        add(
            "obs",
            o,
            f"{o.code.replace('_', ' ').title()}: {o.value:g} {o.unit}{flag}",
            o.observed_at,
        )
    for n in facts(
        ClinicalNote,
        ClinicalNote.note_type.notin_(["TRIAGE"]),
        order=ClinicalNote.recorded_at.desc(),
    ):
        add(
            "note",
            n,
            f"{n.note_type.replace('_', ' ').title()} note: {n.content[:500]}",
            n.recorded_at,
        )

    for r in session.scalars(
        select(InvestigationResult)
        .where(InvestigationResult.patient_id == patient_id)
        .order_by(InvestigationResult.reported_at.desc())
        .limit(MAX_ITEMS_PER_KIND)
    ):
        value = r.value_numeric if r.value_numeric is not None else r.value_text
        flag = (
            ""
            if r.interpretation in ("UNKNOWN", "NORMAL")
            else f", {r.interpretation.replace('_', ' ').lower()}"
        )
        add(
            "res",
            r,
            f"Result {r.test_name}: {value} {r.unit or ''}{flag}".replace("  ", " "),
            r.reported_at,
        )
    for req in session.scalars(
        select(ServiceRequest)
        .where(
            ServiceRequest.patient_id == patient_id,
            ServiceRequest.status.in_(["ORDERED", "RESULTED"]),
        )
        .order_by(ServiceRequest.ordered_at.desc())
        .limit(MAX_ITEMS_PER_KIND)
    ):
        add("order", req, f"Test ordered: {req.name} ({req.status.lower()})", req.ordered_at)
    for rx, item in session.execute(
        select(Prescription, PrescriptionItem)
        .join(PrescriptionItem, PrescriptionItem.prescription_id == Prescription.id)
        .where(Prescription.patient_id == patient_id, Prescription.status == "SIGNED")
        .order_by(Prescription.signed_at.desc())
        .limit(MAX_ITEMS_PER_KIND)
    ):
        detail = ", ".join(x for x in (item.dose, item.route, item.frequency) if x)
        days = f" for {item.duration_days} days" if item.duration_days else ""
        add("rx", item, f"Prescribed: {item.medicine_name} {detail}{days}", rx.signed_at)
    for f in session.scalars(
        select(FollowUp).where(FollowUp.patient_id == patient_id, FollowUp.status == "PENDING")
    ):
        out.append(
            {
                "ref": f"followup:{f.id}",
                "text": f"Follow-up due {f.due_date}: {f.reason}",
                "date": f.due_date.isoformat(),
            }
        )
    return out


def keyword_matches(
    question: str, items: list[dict[str, Any]], limit: int = 8
) -> list[dict[str, Any]]:
    words = {w for w in _WORD.findall(question.casefold()) if w not in _STOP}
    scored = []
    for item in items:
        overlap = len(words & set(_WORD.findall(item["text"].casefold())))
        if overlap:
            scored.append((overlap, item.get("date") or "", item))
    scored.sort(key=lambda t: t[1], reverse=True)  # newest first among equals
    scored.sort(key=lambda t: t[0], reverse=True)  # then best match first (stable)
    return [i for _, _, i in scored[:limit]]


def vet_statements(
    raw: list[dict[str, Any]], items: list[dict[str, Any]]
) -> tuple[list[StatementOut], dict[str, int]]:
    by_ref = {i["ref"]: i for i in items}
    dropped: dict[str, int] = {}
    kept: list[StatementOut] = []

    def drop(why: str) -> None:
        dropped[why] = dropped.get(why, 0) + 1

    for r in raw:
        try:
            st = _Stmt.model_validate(r)
        except ValidationError:
            drop("invalid")
            continue
        if any(ref not in by_ref for ref in st.refs):
            drop("unknown_citation")
            continue
        if guardrails.claims_autonomous_action(st.text):
            drop("claims_action")
            continue
        kept.append(
            StatementOut(
                text=st.text.strip(),
                citations=[
                    CitationOut(
                        ref=ref, label=by_ref[ref]["text"][:80], date=by_ref[ref].get("date")
                    )
                    for ref in dict.fromkeys(st.refs)
                ],
            )
        )
        if len(kept) >= MAX_STATEMENTS:
            break
    return kept, dropped


def ask(
    session: Session, principal: Principal, settings: Settings, patient_id: uuid.UUID, question: str
) -> AskOut:
    assert principal.org_id is not None
    if session.get(Patient, patient_id) is None:
        raise NotFound("Patient not found")
    items = build_items(session, patient_id)
    matches = [
        MatchOut(ref=i["ref"], text=i["text"], date=i.get("date"))
        for i in keyword_matches(question, items)
    ]

    policy = load_policy(session, principal.org_id)
    consented = active_consent(session, patient_id, "AI_PROCESSING") is not None
    if not (policy.ai_processing_enabled and consented):
        why = (
            "AI answering is not switched on for this organisation."
            if not policy.ai_processing_enabled
            else "The patient has not consented to AI processing."
        )
        _audit(session, principal, patient_id, used_ai=False)
        return AskOut(
            answer=None,
            answered=False,
            matches=matches,
            used_ai=False,
            message=f"{why} Showing matching entries from the chart.",
        )

    recent = (
        session.scalar(
            select(func.count())
            .select_from(AiUsage)
            .where(
                AiUsage.user_id == principal.user_id,
                AiUsage.feature == "chart_qa",
                AiUsage.created_at > datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        or 0
    )
    if recent >= settings.ai_analyses_per_minute:
        raise TooManyRequests("Too many questions in a minute. Wait a moment and try again.")

    try:
        llm = get_llm(settings.llm_provider, environment=settings.environment)
    except LLMUnavailable:
        return AskOut(
            answer=None,
            answered=False,
            matches=matches,
            used_ai=False,
            message=f"{UNAVAILABLE} Showing matching entries from the chart.",
        )

    payload = {
        "question": question.strip(),
        "items": [{"ref": i["ref"], "text": i["text"], "date": i["date"]} for i in items],
    }
    system, prompt = render_chart_qa(payload)
    request = LLMRequest("chart_qa", CHART_QA_VERSION, system, prompt, payload, max_tokens=1500)

    def fail(status: str, resp: Any = None) -> AskOut:
        record_usage(session, principal, "chart_qa", llm, resp, status, None, None, patient_id)
        _audit(session, principal, patient_id, used_ai=True)
        return AskOut(
            answer=None,
            answered=False,
            matches=matches,
            used_ai=False,
            message=f"{UNAVAILABLE} Showing matching entries from the chart.",
            is_development=llm.is_development,
        )

    try:
        resp = call_llm(llm, request, settings.llm_timeout_seconds)
    except TimeoutError:
        return fail("TIMEOUT")
    except Exception:  # noqa: BLE001  (a vendor failure must never break the consultation)
        return fail("ERROR")
    try:
        envelope = _Envelope.model_validate(parse_json_object(resp.text))
    except (ValueError, ValidationError):
        return fail("INVALID", resp)

    statements, _ = vet_statements(envelope.statements, items)
    record_usage(session, principal, "chart_qa", llm, resp, "OK", None, None, patient_id)
    _audit(session, principal, patient_id, used_ai=True)
    return AskOut(
        answer=statements,
        answered=bool(statements),
        matches=matches,
        used_ai=True,
        message=None if statements else "This could not be answered from the recorded chart.",
        is_development=llm.is_development,
    )


def _audit(session: Session, principal: Principal, patient_id: uuid.UUID, *, used_ai: bool) -> None:
    assert principal.org_id is not None
    record_audit(
        session,
        principal.meta,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        action="AI_CHART_QUESTION",
        resource_type="patient",
        resource_id=patient_id,
        ai_involved=used_ai,
    )
    session.commit()
