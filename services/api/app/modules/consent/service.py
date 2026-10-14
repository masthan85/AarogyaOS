import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import AppError, Conflict, NotFound
from app.modules.audit.service import emit_event, record_audit
from app.modules.consent.models import PURPOSES, Consent, ConsentPolicy
from app.modules.consent.queries import (
    DEPENDS_ON,
    active_consent,
    current_policy,
    latest_consent,
)
from app.modules.consent.schemas import (
    ConsentIn,
    ConsentOut,
    PatientConsents,
    PolicyIn,
    PurposeStatus,
)
from app.modules.interactions import service as interactions
from app.modules.patients.models import Patient
from app.modules.patients.normalise import age_years
from app.modules.tenancy.policy import load_policy

# Plain statements of what each purpose means. They are STARTING POINTS: installed with
# legally_reviewed = false, and an organisation must have counsel review and republish them.
_END = " You can change your mind and withdraw this at any time by telling the clinic staff."
TEMPLATES: dict[str, tuple[str, str]] = {
    "MEDICAL_CARE": (
        "Consent to medical care",
        "I agree to be examined and treated by the doctors and staff of this clinic, and for my "
        "health information to be written in my medical record." + _END,
    ),
    "AUDIO_RECORDING": (
        "Consent to record the conversation",
        "I agree that the sound of my conversations with clinic staff during this visit may be "
        "recorded so that notes can be prepared. Recording only runs while staff have started it, "
        "and the screen shows clearly when it is on." + _END,
    ),
    "SPEECH_TRANSCRIPTION": (
        "Consent to turn speech into text",
        "I agree that what is said during the recorded conversation may be converted into written "
        "text by a speech-recognition service so that it can be added to my record." + _END,
    ),
    "AI_PROCESSING": (
        "Consent to computer assistance with notes",
        "I agree that computer programs may read the written text of my conversation to suggest "
        "notes and reminders to my doctor. The doctor checks everything and makes every decision "
        "about my care; the software does not." + _END,
    ),
    "AUDIO_RETENTION": (
        "Consent to keep the audio for a limited time",
        "I agree that the audio of my conversation may be kept for a limited period, as explained "
        "to me, instead of being deleted straight after it is turned into text." + _END,
    ),
    "RESEARCH": (
        "Optional: use in research",
        "I agree that information from my visits may be used in approved research. This is "
        "optional and saying no does not affect my care in any way." + _END,
    ),
    "ANALYTICS": (
        "Optional: use to understand how the clinic is working",
        "I agree that information from my visits may be used to understand and improve how the "
        "clinic runs. This is optional and saying no does not affect my care in any way." + _END,
    ),
    "AI_MODEL_IMPROVEMENT": (
        "Optional: use to improve the software",
        "I agree that my recordings or text may be used to improve the speech and assistance "
        "software. This is separate from recording my visit, is optional, and saying no does "
        "not affect my care in any way." + _END,
    ),
}


def _org(principal: Principal) -> uuid.UUID:
    assert principal.org_id is not None
    return principal.org_id


def install_templates(session: Session, principal: Principal, language: str) -> list[ConsentPolicy]:
    created: list[ConsentPolicy] = []
    for purpose, (title, body) in TEMPLATES.items():
        if current_policy_exact(session, purpose, language):
            continue
        created.append(_publish(session, principal, purpose, language, title, body, False))
    record_audit(
        session,
        principal.meta,
        org_id=_org(principal),
        actor_user_id=principal.user_id,
        action="CONSENT_TEMPLATES_INSTALLED",
        resource_type="consent_policy",
        after={"created": len(created), "language": language},
    )
    session.commit()
    return created


def current_policy_exact(session: Session, purpose: str, language: str) -> ConsentPolicy | None:
    return session.scalars(
        select(ConsentPolicy)
        .where(
            ConsentPolicy.purpose == purpose,
            ConsentPolicy.language == language,
            ConsentPolicy.status == "ACTIVE",
        )
        .limit(1)
    ).first()


def _publish(
    session: Session,
    principal: Principal,
    purpose: str,
    language: str,
    title: str,
    body: str,
    reviewed: bool,
) -> ConsentPolicy:
    latest = session.scalar(
        select(func.max(ConsentPolicy.version)).where(
            ConsentPolicy.purpose == purpose, ConsentPolicy.language == language
        )
    )
    for old in session.scalars(
        select(ConsentPolicy).where(
            ConsentPolicy.purpose == purpose,
            ConsentPolicy.language == language,
            ConsentPolicy.status == "ACTIVE",
        )
    ):
        old.status = "RETIRED"  # consents already given keep pointing at the version they saw
    policy = ConsentPolicy(
        organisation_id=_org(principal),
        purpose=purpose,
        language=language,
        version=(latest or 0) + 1,
        title=title,
        body=body,
        legally_reviewed=reviewed,
        created_by=principal.user_id,
    )
    session.add(policy)
    session.flush()
    return policy


def create_policy(session: Session, principal: Principal, body: PolicyIn) -> ConsentPolicy:
    policy = _publish(
        session,
        principal,
        body.purpose,
        body.language,
        body.title,
        body.body,
        body.legally_reviewed,
    )
    record_audit(
        session,
        principal.meta,
        org_id=_org(principal),
        actor_user_id=principal.user_id,
        action="CONSENT_POLICY_PUBLISHED",
        resource_type="consent_policy",
        resource_id=policy.id,
        after={"purpose": policy.purpose, "version": policy.version},
    )
    session.commit()
    return policy


def list_policies(session: Session, include_retired: bool) -> list[ConsentPolicy]:
    stmt = select(ConsentPolicy)
    if not include_retired:
        stmt = stmt.where(ConsentPolicy.status == "ACTIVE")
    return list(
        session.scalars(
            stmt.order_by(
                ConsentPolicy.purpose, ConsentPolicy.language, ConsentPolicy.version.desc()
            )
        )
    )


def _patient(session: Session, patient_id: uuid.UUID) -> Patient:
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise NotFound("Patient not found")
    return patient


def patient_consents(
    session: Session, principal: Principal, patient_id: uuid.UUID
) -> PatientConsents:
    patient = _patient(session, patient_id)
    policy = load_policy(session, _org(principal))
    age = age_years(patient.date_of_birth, date.today())
    statuses: list[PurposeStatus] = []
    for purpose in PURPOSES:
        own = latest_consent(session, patient_id, purpose)
        active = active_consent(session, patient_id, purpose)
        parent = DEPENDS_ON.get(purpose)
        blocked = (
            parent
            if (
                own
                and own.status == "GRANTED"
                and not active
                and parent
                and not active_consent(session, patient_id, parent)
            )
            else None
        )
        statuses.append(
            PurposeStatus(
                purpose=purpose,
                active=active is not None,
                consent_id=active.id if active else None,
                policy_version=active.policy_version if active else None,
                granted_at=active.granted_at if active else None,
                granted_by_type=active.granted_by_type if active else None,
                blocked_by=blocked,
                wording_available=current_policy(session, purpose, patient.preferred_language)
                is not None,
            )
        )
    history = session.scalars(
        select(Consent)
        .where(Consent.patient_id == patient_id)
        .order_by(Consent.granted_at.desc())
        .limit(100)
    ).all()
    return PatientConsents(
        status=statuses,
        history=[ConsentOut.model_validate(c) for c in history],
        guardian_required=age is not None and age < policy.guardian_consent_under_age,
    )


def capture_consent(
    session: Session, principal: Principal, patient_id: uuid.UUID, body: ConsentIn
) -> ConsentOut:
    org_id = _org(principal)
    patient = _patient(session, patient_id)
    policy_cfg = load_policy(session, org_id)
    language = body.language_presented or patient.preferred_language
    if body.policy_id:
        policy = session.get(ConsentPolicy, body.policy_id)
        if policy is None or policy.purpose != body.purpose or policy.status != "ACTIVE":
            raise AppError("That wording is not the current wording for this purpose")
    else:
        policy = current_policy(session, body.purpose, language)
        if policy is None:
            raise Conflict(
                f"No consent wording has been published for {body.purpose}. "
                "An administrator must publish it first."
            )
    age = age_years(patient.date_of_birth, date.today())
    if (
        age is not None
        and age < policy_cfg.guardian_consent_under_age
        and body.granted_by_type != "REPRESENTATIVE"
    ):
        raise AppError("This patient is a minor: consent must be given by a parent or guardian")
    parent = DEPENDS_ON.get(body.purpose)
    if parent and active_consent(session, patient_id, parent) is None:
        raise Conflict(f"Consent for {parent} is needed first")
    if active_consent(session, patient_id, body.purpose) is not None:
        raise Conflict("This consent has already been given")
    consent = Consent(
        organisation_id=org_id,
        patient_id=patient_id,
        purpose=body.purpose,
        policy_id=policy.id,
        policy_version=policy.version,
        granted_by_type=body.granted_by_type,
        representative_name=body.representative_name,
        representative_relationship=body.representative_relationship,
        method=body.method,
        language_presented=policy.language,
        captured_by=principal.user_id,
        encounter_id=body.encounter_id,
    )
    session.add(consent)
    session.flush()
    emit_event(
        session,
        org_id=org_id,
        event_type="CONSENT_GRANTED",
        aggregate_type="consent",
        aggregate_id=consent.id,
        patient_id=patient_id,
        actor_user_id=principal.user_id,
        payload={"purpose": body.purpose, "version": policy.version, "by": body.granted_by_type},
    )
    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action="CONSENT_GRANTED",
        resource_type="consent",
        resource_id=consent.id,
        after={"purpose": body.purpose, "version": policy.version, "by": body.granted_by_type},
    )
    session.commit()
    return ConsentOut.model_validate(consent)


def withdraw_consent(
    session: Session, principal: Principal, consent_id: uuid.UUID, reason: str | None
) -> ConsentOut:
    org_id = _org(principal)
    consent = session.scalar(select(Consent).where(Consent.id == consent_id).with_for_update())
    if consent is None:
        raise NotFound("Consent not found")
    if consent.status != "GRANTED":
        raise Conflict("This consent has already been withdrawn")
    consent.status = "WITHDRAWN"
    consent.withdrawn_at = datetime.now(UTC)
    consent.withdrawn_by = principal.user_id
    consent.withdrawal_reason = reason
    session.flush()
    effects = interactions.on_consent_withdrawn(session, principal, consent)
    emit_event(
        session,
        org_id=org_id,
        event_type="CONSENT_WITHDRAWN",
        aggregate_type="consent",
        aggregate_id=consent.id,
        patient_id=consent.patient_id,
        actor_user_id=principal.user_id,
        payload={"purpose": consent.purpose, **effects},
    )
    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action="CONSENT_WITHDRAWN",
        resource_type="consent",
        resource_id=consent.id,
        after={"purpose": consent.purpose, **effects},
    )
    session.commit()
    return ConsentOut.model_validate(consent)
