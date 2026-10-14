import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.context import Principal
from app.core.errors import AppError, Conflict, Forbidden, NotFound, ServiceUnavailable
from app.modules.audit.service import emit_event, record_audit
from app.modules.clinical.encounters import OPEN, practitioner_for, require_owner
from app.modules.clinical.models import Encounter
from app.modules.consent.models import Consent
from app.modules.consent.queries import active_consent, missing_consents
from app.modules.interactions.models import (
    AudioAsset,
    ClinicalInteraction,
    InteractionSpeaker,
    SpeechUsage,
    TranscriptSegment,
)
from app.modules.interactions.schemas import (
    InteractionCreate,
    PartialOut,
    SegmentOut,
    SpeakerOut,
    TranscriptOut,
    UsageRow,
)
from app.modules.patients.models import Patient
from app.modules.scheduling.models import Appointment
from app.modules.tenancy.policy import OrgPolicy, load_policy
from app.speech import live
from app.speech.provider import (
    ProviderNotAvailable,
    ProviderStats,
    RecognisedSegment,
    SpeechProvider,
)
from app.speech.registry import get_provider

PURPOSE_PERMISSION = {
    "RECEPTION": "interaction:reception",
    "TRIAGE": "interaction:triage",
    "CONSULTATION": "interaction:consultation",
}
LIVE = ("CREATED", "ACTIVE", "PAUSED")
RECEPTION_STATES = ("BOOKED", "CONFIRMED", "ARRIVED", "CHECKED_IN", "WAITING")
# An ACTIVE session whose audio stopped arriving is not really recording: say so.
STALE_AFTER = timedelta(seconds=45)


class ConsentRequired(AppError):
    status_code = 409
    code = "consent_required"


def _org(principal: Principal) -> uuid.UUID:
    assert principal.org_id is not None
    return principal.org_id


def required_purposes(ai_processing: bool) -> list[str]:
    needed = ["AUDIO_RECORDING", "SPEECH_TRANSCRIPTION"]
    return needed + ["AI_PROCESSING"] if ai_processing else needed


def get_interaction(
    session: Session, interaction_id: uuid.UUID, *, lock: bool = False
) -> ClinicalInteraction:
    stmt = select(ClinicalInteraction).where(ClinicalInteraction.id == interaction_id)
    row = session.scalar(stmt.with_for_update() if lock else stmt)
    if row is None:
        raise NotFound("Recording session not found")
    return row


def can_access(session: Session, principal: Principal, ia: ClinicalInteraction) -> bool:
    """Whoever ran the session, or the doctor responsible for the encounter. Nobody else."""
    if ia.started_by == principal.user_id:
        return True
    if ia.encounter_id is None:
        return False
    enc = session.get(Encounter, ia.encounter_id)
    me = practitioner_for(session, principal)
    return bool(enc and me and enc.practitioner_id == me.id)


def visible(
    session: Session, principal: Principal, interaction_id: uuid.UUID, *, lock: bool = False
) -> ClinicalInteraction:
    ia = get_interaction(session, interaction_id, lock=lock)
    if not can_access(session, principal, ia):
        raise NotFound("Recording session not found")  # do not reveal that it exists
    return ia


def _provider(settings: Settings) -> SpeechProvider:
    try:
        return get_provider(settings.speech_provider, environment=settings.environment)
    except ProviderNotAvailable as exc:
        raise ServiceUnavailable(str(exc)) from exc


def _check_consent(session: Session, patient_id: uuid.UUID, ai_processing: bool) -> None:
    missing = missing_consents(session, patient_id, required_purposes(ai_processing))
    if missing:
        raise ConsentRequired(
            "The patient has not given the consent needed to record: " + ", ".join(missing),
            extra={"missing": missing},
        )


def _check_policy(policy: OrgPolicy, ai_processing: bool) -> None:
    if not policy.recording_enabled:
        raise Conflict("Recording is not enabled for this organisation")
    if ai_processing and not policy.ai_processing_enabled:
        raise Conflict("AI processing is not enabled for this organisation")


def create_interaction(
    session: Session, principal: Principal, settings: Settings, body: InteractionCreate
) -> ClinicalInteraction:
    org_id = _org(principal)
    if not principal.has(PURPOSE_PERMISSION[body.purpose]):
        raise Forbidden("You cannot record this kind of conversation")
    policy = load_policy(session, org_id)
    _check_policy(policy, body.ai_processing)
    patient = session.get(Patient, body.patient_id)
    if patient is None or patient.status != "ACTIVE":
        raise NotFound("Patient not found")

    encounter_id = appointment_id = None
    if body.purpose == "RECEPTION":
        if body.appointment_id is None or body.encounter_id is not None:
            raise AppError("A reception recording needs the patient's appointment")
        appt = session.get(Appointment, body.appointment_id)
        if appt is None or appt.patient_id != patient.id or appt.status not in RECEPTION_STATES:
            raise Conflict("This is not an open visit for this patient")
        appointment_id = appt.id
    else:
        if body.encounter_id is None:
            raise AppError("Open the encounter before recording")
        enc = session.get(Encounter, body.encounter_id)
        if enc is None or enc.patient_id != patient.id:
            raise NotFound("Encounter not found")
        if body.purpose == "CONSULTATION":
            if enc.status != "IN_PROGRESS":
                raise Conflict("The consultation has not started")
            require_owner(session, principal, enc)
        elif enc.status not in OPEN:
            raise Conflict("This visit is closed")
        encounter_id, appointment_id = enc.id, enc.appointment_id

    _check_consent(session, patient.id, body.ai_processing)
    provider = _provider(settings)

    busy = session.scalar(
        select(ClinicalInteraction.id).where(
            ClinicalInteraction.status.in_(("ACTIVE", "PAUSED")),
            ClinicalInteraction.started_by == principal.user_id,
        )
    )
    if busy:
        raise Conflict("You already have a recording in progress. Stop it first.")
    duplicate = session.scalar(
        select(ClinicalInteraction.id).where(
            ClinicalInteraction.status.in_(LIVE),
            ClinicalInteraction.purpose == body.purpose,
            ClinicalInteraction.patient_id == patient.id,
            ClinicalInteraction.encounter_id.is_(None)
            if encounter_id is None
            else ClinicalInteraction.encounter_id == encounter_id,
        )
    )
    if duplicate:
        raise Conflict("A recording for this visit is already open")

    retention_consent = active_consent(session, patient.id, "AUDIO_RETENTION")
    ids = [
        str(c.id)
        for p in required_purposes(body.ai_processing)
        if (c := active_consent(session, patient.id, p))
    ]
    ia = ClinicalInteraction(
        organisation_id=org_id,
        patient_id=patient.id,
        encounter_id=encounter_id,
        appointment_id=appointment_id,
        purpose=body.purpose,
        started_by=principal.user_id,
        language_hint=body.language_hint or patient.preferred_language or "auto",
        ai_processing=body.ai_processing,
        consent_ids=ids,
        speech_provider=provider.name,
        speech_model=provider.model,
        is_development=provider.is_development,
        retain_audio=policy.audio_retention == "RETAIN_DAYS" and retention_consent is not None,
    )
    session.add(ia)
    session.flush()
    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action="INTERACTION_CREATED",
        resource_type="interaction",
        resource_id=ia.id,
        after={
            "purpose": ia.purpose,
            "provider": ia.speech_provider,
            "ai": ia.ai_processing,
            "retain_audio": ia.retain_audio,
        },
    )
    session.commit()
    return ia


def _event(
    session: Session,
    principal: Principal,
    ia: ClinicalInteraction,
    event: str,
    payload: dict[str, object] | None = None,
) -> None:
    org_id = _org(principal)
    emit_event(
        session,
        org_id=org_id,
        event_type=event,
        aggregate_type="interaction",
        aggregate_id=ia.id,
        patient_id=ia.patient_id,
        encounter_id=ia.encounter_id,
        actor_user_id=principal.user_id,
        payload=payload,
    )
    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action=event,
        resource_type="interaction",
        resource_id=ia.id,
        after=payload,
    )


def start(session: Session, principal: Principal, interaction_id: uuid.UUID) -> ClinicalInteraction:
    ia = visible(session, principal, interaction_id, lock=True)
    if ia.started_by != principal.user_id:
        raise Forbidden("Only the person who set up the recording can start it")
    if ia.status == "ENDED":
        why = " because consent was withdrawn" if ia.end_reason == "CONSENT_WITHDRAWN" else ""
        raise Conflict(f"This recording has ended{why}")
    if ia.status != "CREATED":
        raise Conflict("This recording has already been started")
    _check_policy(load_policy(session, ia.organisation_id), ia.ai_processing)
    _check_consent(session, ia.patient_id, ia.ai_processing)  # consent may have changed since setup
    now = datetime.now(UTC)
    ia.status, ia.recording_started_at, ia.last_audio_at = "ACTIVE", now, now
    _event(session, principal, ia, "INTERACTION_STARTED", {"purpose": ia.purpose})
    _event(session, principal, ia, "RECORDING_STARTED")
    session.commit()
    return ia


def pause(
    session: Session, principal: Principal, interaction_id: uuid.UUID, reason: str = "USER"
) -> ClinicalInteraction:
    ia = visible(session, principal, interaction_id, lock=True)
    if ia.status != "ACTIVE":
        raise Conflict("Only an active recording can be paused")
    ia.status, ia.pause_reason = "PAUSED", reason
    _event(session, principal, ia, "RECORDING_PAUSED", {"reason": reason})
    session.commit()
    return ia


def pause_system(
    session: Session, principal: Principal, ia: ClinicalInteraction, reason: str
) -> None:
    """Pause because the recording can no longer be trusted to be running (dropped connection,
    provider failure, time limit). The screen must stop saying 'recording' when it is not."""
    if ia.status == "ACTIVE":
        ia.status, ia.pause_reason = "PAUSED", reason
        _event(session, principal, ia, "RECORDING_PAUSED", {"reason": reason})
        session.commit()


def resume(
    session: Session, principal: Principal, interaction_id: uuid.UUID
) -> ClinicalInteraction:
    ia = visible(session, principal, interaction_id, lock=True)
    if ia.status != "PAUSED":
        raise Conflict("Only a paused recording can be resumed")
    if ia.started_by != principal.user_id:
        raise Forbidden("Only the person who set up the recording can resume it")
    _check_policy(load_policy(session, ia.organisation_id), ia.ai_processing)
    _check_consent(session, ia.patient_id, ia.ai_processing)
    ia.status, ia.pause_reason, ia.last_audio_at = "ACTIVE", None, datetime.now(UTC)
    _event(session, principal, ia, "RECORDING_RESUMED")
    session.commit()
    return ia


def _end(session: Session, principal: Principal, ia: ClinicalInteraction, reason: str) -> None:
    now = datetime.now(UTC)
    was_recording = ia.status in ("ACTIVE", "PAUSED")
    ia.status, ia.end_reason, ia.ended_at = "ENDED", reason, now
    live.clear(ia.id)
    if ia.retain_audio:
        policy = load_policy(session, ia.organisation_id)
        ia.retain_until = now + timedelta(days=policy.retain_days)
        for asset in session.scalars(select(AudioAsset).where(AudioAsset.interaction_id == ia.id)):
            asset.retain_until = ia.retain_until
    count = (
        session.scalar(
            select(func.count())
            .select_from(TranscriptSegment)
            .where(TranscriptSegment.interaction_id == ia.id)
        )
        or 0
    )
    if was_recording:
        _event(session, principal, ia, "RECORDING_STOPPED", {"reason": reason})
    _event(session, principal, ia, "TRANSCRIPT_UPDATED", {"segments": count})


def stop(
    session: Session, principal: Principal, interaction_id: uuid.UUID, reason: str | None
) -> ClinicalInteraction:
    ia = visible(session, principal, interaction_id, lock=True)
    if ia.status == "ENDED":
        return ia  # idempotent: a double tap must not fail
    _end(session, principal, ia, reason or "USER")
    session.commit()
    return ia


def on_consent_withdrawn(
    session: Session, principal: Principal, consent: Consent
) -> dict[str, int]:
    """Withdrawal is immediate: live sessions end; retained audio is queued for deletion."""
    ended = purged = 0
    purpose = consent.purpose
    if purpose in ("AUDIO_RECORDING", "SPEECH_TRANSCRIPTION", "AI_PROCESSING"):
        stmt = (
            select(ClinicalInteraction)
            .where(
                ClinicalInteraction.patient_id == consent.patient_id,
                ClinicalInteraction.status.in_(LIVE),
            )
            .with_for_update()
        )
        if purpose == "AI_PROCESSING":
            stmt = stmt.where(ClinicalInteraction.ai_processing.is_(True))
        for ia in session.scalars(stmt):
            _end(session, principal, ia, "CONSENT_WITHDRAWN")
            ended += 1
    if purpose in ("AUDIO_RECORDING", "AUDIO_RETENTION"):
        now = datetime.now(UTC)
        for asset in session.scalars(
            select(AudioAsset).where(
                AudioAsset.patient_id == consent.patient_id, AudioAsset.deleted_at.is_(None)
            )
        ):
            asset.purge_requested_at, asset.purge_reason = now, "CONSENT_WITHDRAWN"
            purged += 1
        for ia in session.scalars(
            select(ClinicalInteraction).where(
                ClinicalInteraction.patient_id == consent.patient_id,
                ClinicalInteraction.retain_audio.is_(True),
                ClinicalInteraction.status.in_(LIVE),
            )
        ):
            ia.retain_audio = False
    return {"sessions_ended": ended, "audio_purge_requested": purged}


def reconcile_stale(session: Session, ia: ClinicalInteraction) -> None:
    """If audio stopped arriving, stop claiming that we are recording."""
    if (
        ia.status == "ACTIVE"
        and ia.last_audio_at
        and datetime.now(UTC) - ia.last_audio_at > STALE_AFTER
    ):
        ia.status, ia.pause_reason = "PAUSED", "CONNECTION_LOST"
        session.commit()


def list_for_patient(
    session: Session, principal: Principal, patient_id: uuid.UUID
) -> list[ClinicalInteraction]:
    rows = session.scalars(
        select(ClinicalInteraction)
        .where(ClinicalInteraction.patient_id == patient_id)
        .order_by(ClinicalInteraction.created_at.desc())
        .limit(50)
    ).all()
    return [r for r in rows if can_access(session, principal, r)]


# ---- transcript --------------------------------------------------------------------


def _speaker_rows(session: Session, interaction_id: uuid.UUID) -> dict[str, InteractionSpeaker]:
    return {
        s.speaker_id: s
        for s in session.scalars(
            select(InteractionSpeaker).where(InteractionSpeaker.interaction_id == interaction_id)
        )
    }


def add_segment(
    session: Session,
    ia: ClinicalInteraction,
    seg: RecognisedSegment,
    seq: int,
    provider: SpeechProvider,
) -> TranscriptSegment:
    """Persist one FINAL segment exactly as recognised. Called only by the audio gateway."""
    row = TranscriptSegment(
        organisation_id=ia.organisation_id,
        interaction_id=ia.id,
        patient_id=ia.patient_id,
        seq=seq,
        speaker_id=seg.speaker_id,
        start_ms=seg.start_ms,
        end_ms=seg.end_ms,
        raw_text=seg.text,
        language=seg.language,
        secondary_language=seg.secondary_language,
        language_confidence=seg.language_confidence,
        confidence=seg.confidence,
        code_switch_spans=[
            {"start": s.start_char, "end": s.end_char, "language": s.language}
            for s in seg.code_switch_spans
        ],
        provider=provider.name,
        provider_model=provider.model,
    )
    session.add(row)
    if seg.speaker_id and session.get(InteractionSpeaker, (ia.id, seg.speaker_id)) is None:
        # Everyone starts as UNKNOWN: a person decides who is who, never the order of speaking.
        session.add(
            InteractionSpeaker(
                interaction_id=ia.id,
                speaker_id=seg.speaker_id,
                organisation_id=ia.organisation_id,
                role="UNKNOWN",
            )
        )
    session.commit()
    return row


def transcript(
    session: Session,
    principal: Principal,
    interaction_id: uuid.UUID,
    after_seq: int,
    *,
    audit_view: bool = True,
) -> TranscriptOut:
    ia = visible(session, principal, interaction_id)
    reconcile_stale(session, ia)
    speakers = _speaker_rows(session, ia.id)
    rows = session.scalars(
        select(TranscriptSegment)
        .where(TranscriptSegment.interaction_id == ia.id, TranscriptSegment.seq > after_seq)
        .order_by(TranscriptSegment.seq)
        .limit(500)
    ).all()
    if (
        after_seq == 0 and audit_view
    ):  # the initial open is audited; the 1-second polling after it is not
        record_audit(
            session,
            principal.meta,
            org_id=ia.organisation_id,
            actor_user_id=principal.user_id,
            action="TRANSCRIPT_VIEWED",
            resource_type="interaction",
            resource_id=ia.id,
        )
        session.commit()
    partial = live.get_partial(ia.id) if ia.status == "ACTIVE" else None
    return TranscriptOut(
        interaction_id=ia.id,
        status=ia.status,
        is_development=ia.is_development,
        ai_processing=ia.ai_processing,
        segments=[
            SegmentOut(
                id=r.id,
                seq=r.seq,
                speaker_id=r.speaker_id,
                speaker_role=speakers[r.speaker_id].role if r.speaker_id in speakers else "UNKNOWN",
                start_ms=r.start_ms,
                end_ms=r.end_ms,
                raw_text=r.raw_text,
                normalised_text=r.normalised_text,
                language=r.language,
                secondary_language=r.secondary_language,
                language_confidence=r.language_confidence,
                confidence=r.confidence,
                code_switch_spans=r.code_switch_spans,
                provider=r.provider,
            )
            for r in rows
        ],
        speakers=[
            SpeakerOut(speaker_id=s.speaker_id, role=s.role, label=s.label)
            for s in sorted(speakers.values(), key=lambda s: s.speaker_id)
        ],
        partial=PartialOut(
            text=partial.text, speaker_id=partial.speaker_id, language=partial.language
        )
        if partial
        else None,
        last_seq=rows[-1].seq if rows else after_seq,
    )


def assign_speaker(
    session: Session,
    principal: Principal,
    interaction_id: uuid.UUID,
    speaker_id: str,
    role: str,
    label: str | None,
) -> SpeakerOut:
    ia = visible(session, principal, interaction_id)
    speaker = session.get(InteractionSpeaker, (ia.id, speaker_id))
    if speaker is None:
        raise NotFound("Speaker not found in this recording")
    before: dict[str, object] = {"role": speaker.role, "label": speaker.label}
    speaker.role, speaker.label = role, label
    speaker.assigned_by, speaker.assigned_at = principal.user_id, datetime.now(UTC)
    record_audit(
        session,
        principal.meta,
        org_id=ia.organisation_id,
        actor_user_id=principal.user_id,
        action="SPEAKER_ROLE_ASSIGNED",
        resource_type="interaction",
        resource_id=ia.id,
        before=before,
        after={"role": role, "label": label},
    )
    session.commit()
    return SpeakerOut(speaker_id=speaker.speaker_id, role=speaker.role, label=speaker.label)


# ---- usage -------------------------------------------------------------------------


def record_usage(session: Session, ia: ClinicalInteraction, stats: ProviderStats) -> None:
    usage = session.scalar(select(SpeechUsage).where(SpeechUsage.interaction_id == ia.id))
    if usage is None:
        usage = SpeechUsage(
            organisation_id=ia.organisation_id,
            interaction_id=ia.id,
            patient_id=ia.patient_id,
            encounter_id=ia.encounter_id,
            user_id=ia.started_by,
            provider=stats.provider,
            model=stats.model,
            audio_seconds=0,
            segments=0,
            errors=0,
        )
        session.add(usage)
    usage.audio_seconds += stats.audio_seconds
    usage.segments += stats.segments
    usage.errors += stats.errors
    usage.provider, usage.model = stats.provider, stats.model
    if stats.fell_back_from:
        usage.fell_back_from = stats.fell_back_from
    if usage.first_segment_latency_ms is None:
        usage.first_segment_latency_ms = stats.first_segment_latency_ms
    ia.audio_seconds = usage.audio_seconds
    session.commit()


def usage_summary(session: Session, since: datetime, until: datetime) -> list[UsageRow]:
    rows = session.execute(
        select(
            SpeechUsage.provider,
            SpeechUsage.model,
            func.count(),
            func.sum(SpeechUsage.audio_seconds),
            func.sum(SpeechUsage.segments),
            func.sum(SpeechUsage.errors),
            func.count(SpeechUsage.fell_back_from),
            func.avg(SpeechUsage.first_segment_latency_ms),
            func.sum(SpeechUsage.estimated_cost_paise),
        )
        .where(SpeechUsage.created_at >= since, SpeechUsage.created_at < until)
        .group_by(SpeechUsage.provider, SpeechUsage.model)
    ).all()
    return [
        UsageRow(
            provider=r[0],
            model=r[1],
            sessions=r[2],
            audio_seconds=float(r[3] or 0),
            segments=int(r[4] or 0),
            errors=int(r[5] or 0),
            fallbacks=int(r[6] or 0),
            avg_first_segment_latency_ms=float(r[7]) if r[7] is not None else None,
            estimated_cost_paise=int(r[8]) if r[8] is not None else None,
        )
        for r in rows
    ]
