import uuid
from datetime import date

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.crypto import FieldCrypto
from app.core.errors import AppError, Conflict, NotFound
from app.modules.audit.models import ClinicalEvent
from app.modules.audit.service import emit_event, record_audit
from app.modules.patients.models import (
    MrnCounter,
    Patient,
    PatientIdentifier,
    PatientLanguage,
    PatientRevision,
)
from app.modules.patients.normalise import (
    age_years,
    dob_from_age,
    mask_mobile,
    normalise_name,
)
from app.modules.patients.schemas import (
    DuplicateCandidate,
    IdentifierIn,
    IdentifierOut,
    PatientCreate,
    PatientHit,
    PatientOut,
    PatientUpdate,
    RevealedIdentifier,
    TimelineEvent,
)

MAX_SEARCH_RESULTS = 20
# Fields that may be edited; each change keeps the previous value in patient_revisions.
_EDITABLE = (
    "full_name",
    "date_of_birth",
    "administrative_gender",
    "sex_at_birth",
    "mobile",
    "address",
    "emergency_contact_name",
    "emergency_contact_phone",
    "emergency_contact_relationship",
    "preferred_language",
    "communication_prefs",
)


class PossibleDuplicate(AppError):
    status_code = 409
    code = "possible_duplicate"


def _org(principal: Principal) -> uuid.UUID:
    assert principal.org_id is not None
    return principal.org_id


def _ident_context(system: str) -> str:
    return f"patient-identifier:{system}"


def _hint(system: str, value: str) -> str:
    if system == "ABHA_NUMBER":
        return f"XX-XXXX-XXXX-{value[-4:]}"
    return f"…{value[-4:]}" if len(value) > 6 else "…"


def _next_mrn(session: Session, org_id: uuid.UUID) -> str:
    stmt = (
        pg_insert(MrnCounter)
        .values(organisation_id=org_id, last_value=1)
        .on_conflict_do_update(
            index_elements=[MrnCounter.organisation_id],
            set_={"last_value": MrnCounter.last_value + 1},
        )
        .returning(MrnCounter.last_value)
    )
    return f"P{session.execute(stmt).scalar_one():07d}"


def _hit(p: Patient, today: date) -> PatientHit:
    return PatientHit(
        id=p.id,
        mrn=p.mrn,
        full_name=p.full_name,
        age_years=age_years(p.date_of_birth, today),
        administrative_gender=p.administrative_gender,
        mobile_masked=mask_mobile(p.mobile),
    )


def _like_escape(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _out(session: Session, p: Patient) -> PatientOut:
    idents = session.scalars(
        select(PatientIdentifier).where(PatientIdentifier.patient_id == p.id)
    ).all()
    langs = session.scalars(
        select(PatientLanguage.language_tag).where(PatientLanguage.patient_id == p.id)
    ).all()
    out = PatientOut.model_validate(
        {
            **{c: getattr(p, c) for c in PatientOut.model_fields if hasattr(p, c)},
            "age_years": age_years(p.date_of_birth, date.today()),
            "spoken_languages": sorted(langs),
            "identifiers": [
                IdentifierOut(id=i.id, system=i.system, masked=i.display_hint, verified=i.verified)
                for i in idents
            ],
        }
    )
    return out


def find_duplicates(
    session: Session,
    org_id: uuid.UUID,
    *,
    name: str,
    dob: date | None,
    mobile: str | None,
    identifier_indexes: list[tuple[str, str]],
    exclude_id: uuid.UUID | None = None,
) -> list[DuplicateCandidate]:
    """Candidate matches with reasons. Never auto-merges; a human decides."""
    sim = func.similarity(Patient.normalised_name, name)
    conds = [(sim >= 0.8)]
    if dob:
        conds.append((Patient.date_of_birth == dob) & (sim >= 0.45))
    if mobile:
        # Families share mobiles, so a shared number alone is NOT a duplicate signal.
        conds.append((Patient.mobile == mobile) & (sim >= 0.5))
    ident_matches: dict[uuid.UUID, str] = {}
    for system, index in identifier_indexes:
        row = session.execute(
            select(PatientIdentifier.patient_id).where(
                PatientIdentifier.system == system, PatientIdentifier.value_index == index
            )
        ).first()
        if row:
            ident_matches[row[0]] = system
    if ident_matches:
        conds.append(Patient.id.in_(list(ident_matches)))
    stmt = select(Patient, sim).where(Patient.status == "ACTIVE", or_(*conds))
    if exclude_id:
        stmt = stmt.where(Patient.id != exclude_id)
    today = date.today()
    out: list[DuplicateCandidate] = []
    for patient, score in session.execute(stmt.order_by(sim.desc()).limit(5)).all():
        reasons = []
        if patient.id in ident_matches:
            reasons.append(f"same {ident_matches[patient.id]}")
        if dob and patient.date_of_birth == dob:
            reasons.append("same date of birth")
        if mobile and patient.mobile == mobile:
            reasons.append("same mobile number")
        if score >= 0.45:
            reasons.append("similar name")
        out.append(DuplicateCandidate(**_hit(patient, today).model_dump(), reasons=reasons))
    return out


def _prepare_identifiers(
    crypto: FieldCrypto, items: list[IdentifierIn]
) -> list[tuple[IdentifierIn, str]]:
    return [(i, crypto.blind_index(i.value, context=_ident_context(i.system))) for i in items]


def _all_indexes(crypto: FieldCrypto, items: list[IdentifierIn]) -> list[tuple[str, str]]:
    """(system, index) under every configured key, so lookups survive a key rotation."""
    return [
        (i.system, idx)
        for i in items
        for idx in crypto.blind_indexes(i.value, context=_ident_context(i.system))
    ]


def create_patient(
    session: Session, principal: Principal, crypto: FieldCrypto, body: PatientCreate
) -> PatientOut:
    org_id = _org(principal)
    today = date.today()
    dob_estimated = body.date_of_birth is None
    dob = body.date_of_birth or dob_from_age(body.age_years or 0, today)
    name = normalise_name(body.full_name)
    if not name:
        raise AppError("Enter the patient's name")
    prepared = _prepare_identifiers(crypto, body.identifiers)

    if not body.confirm_not_duplicate:
        candidates = find_duplicates(
            session,
            org_id,
            name=name,
            dob=dob,
            mobile=body.mobile,
            identifier_indexes=_all_indexes(crypto, body.identifiers),
        )
        if candidates:
            raise PossibleDuplicate(
                "Possible duplicate patient. Review the matches, then confirm to register anyway.",
                extra={"candidates": [c.model_dump(mode="json") for c in candidates]},
            )

    patient = Patient(
        organisation_id=org_id,
        mrn=_next_mrn(session, org_id),
        full_name=body.full_name.strip(),
        normalised_name=name,
        date_of_birth=dob,
        dob_is_estimated=dob_estimated,
        administrative_gender=body.administrative_gender,
        sex_at_birth=body.sex_at_birth,
        mobile=body.mobile,
        address=body.address,
        emergency_contact_name=body.emergency_contact_name,
        emergency_contact_phone=body.emergency_contact_phone,
        emergency_contact_relationship=body.emergency_contact_relationship,
        preferred_language=body.preferred_language,
        communication_prefs=body.communication_prefs,
        created_by=principal.user_id,
    )
    session.add(patient)
    try:
        session.flush()
        for item, index in prepared:
            session.add(
                PatientIdentifier(
                    organisation_id=org_id,
                    patient_id=patient.id,
                    system=item.system,
                    value_ciphertext=crypto.encrypt(
                        item.value, context=_ident_context(item.system)
                    ),
                    value_index=index,
                    display_hint=_hint(item.system, item.value),
                )
            )
        for tag in body.spoken_languages:
            session.add(
                PatientLanguage(patient_id=patient.id, language_tag=tag, organisation_id=org_id)
            )
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise Conflict("An identifier is already registered to another patient") from exc

    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action="PATIENT_CREATED",
        resource_type="patient",
        resource_id=patient.id,
    )
    emit_event(
        session,
        org_id=org_id,
        event_type="PATIENT_REGISTERED",
        aggregate_type="patient",
        aggregate_id=patient.id,
        patient_id=patient.id,
        actor_user_id=principal.user_id,
    )
    session.commit()
    return _out(session, patient)


def search_patients(
    session: Session,
    principal: Principal,
    *,
    name: str | None,
    mobile: str | None,
    mrn: str | None,
) -> list[PatientHit]:
    """Deliberately narrow: no listing, no wildcard-only queries, tiny result set."""
    from app.modules.patients.normalise import normalise_mobile

    stmt = select(Patient).where(Patient.status == "ACTIVE")
    criteria = 0
    if mrn:
        stmt = stmt.where(Patient.mrn == mrn.strip().upper())
        criteria += 1
    if mobile:
        try:
            stmt = stmt.where(Patient.mobile == normalise_mobile(mobile))
        except ValueError as exc:
            raise AppError(str(exc)) from exc
        criteria += 1
    if name:
        tokens = normalise_name(name).split()
        if not tokens or max(len(t) for t in tokens) < 3:
            raise AppError("Type at least 3 letters of the name")
        for t in tokens:
            esc = _like_escape(t)
            stmt = stmt.where(
                or_(
                    Patient.normalised_name.like(f"{esc}%", escape="\\"),
                    Patient.normalised_name.like(f"% {esc}%", escape="\\"),
                )
            )
        criteria += 1
    if criteria == 0:
        raise AppError("Search by name, mobile number or MRN")
    rows = session.scalars(stmt.order_by(Patient.full_name).limit(MAX_SEARCH_RESULTS)).all()
    # Count only: the query text may itself be PHI, so it never reaches the audit log.
    record_audit(
        session,
        principal.meta,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        action="PATIENT_SEARCHED",
        resource_type="patient",
        after={"results": len(rows)},
    )
    session.commit()
    today = date.today()
    return [_hit(p, today) for p in rows]


def _get(session: Session, patient_id: uuid.UUID, *, lock: bool = False) -> Patient:
    stmt = select(Patient).where(Patient.id == patient_id)
    patient = session.scalar(stmt.with_for_update() if lock else stmt)
    if patient is None:
        raise NotFound("Patient not found")
    return patient


def get_patient(session: Session, principal: Principal, patient_id: uuid.UUID) -> PatientOut:
    patient = _get(session, patient_id)
    record_audit(
        session,
        principal.meta,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        action="PATIENT_VIEWED",
        resource_type="patient",
        resource_id=patient.id,
    )
    session.commit()
    return _out(session, patient)


def update_patient(
    session: Session, principal: Principal, patient_id: uuid.UUID, body: PatientUpdate
) -> PatientOut:
    org_id = _org(principal)
    patient = _get(session, patient_id, lock=True)
    if patient.version != body.expected_version:
        raise Conflict("This record was changed by someone else. Reload and try again.")
    sent = body.model_dump(exclude_unset=True)
    previous: dict[str, object] = {}
    for field in _EDITABLE:
        if field in sent and sent[field] != getattr(patient, field):
            previous[field] = getattr(patient, field)
            setattr(patient, field, sent[field])
            if field == "full_name":
                patient.normalised_name = normalise_name(sent[field])
            if field == "date_of_birth":
                patient.dob_is_estimated = False
    if "spoken_languages" in sent and sent["spoken_languages"] is not None:
        session.execute(delete(PatientLanguage).where(PatientLanguage.patient_id == patient.id))
        for tag in sorted(set(sent["spoken_languages"])):
            session.add(
                PatientLanguage(patient_id=patient.id, language_tag=tag, organisation_id=org_id)
            )
        previous["spoken_languages"] = "changed"
    if previous:
        session.add(
            PatientRevision(
                organisation_id=org_id,
                patient_id=patient.id,
                version=patient.version,
                previous_values=_jsonable(previous),
                changed_by=principal.user_id,
            )
        )
        patient.version += 1
        # Audit stores which fields changed; the old values live in patient_revisions.
        record_audit(
            session,
            principal.meta,
            org_id=org_id,
            actor_user_id=principal.user_id,
            action="PATIENT_UPDATED",
            resource_type="patient",
            resource_id=patient.id,
            after={"changed_fields": sorted(previous)},
        )
        emit_event(
            session,
            org_id=org_id,
            event_type="PATIENT_UPDATED",
            aggregate_type="patient",
            aggregate_id=patient.id,
            patient_id=patient.id,
            actor_user_id=principal.user_id,
            payload={"fields": sorted(previous)},
        )
    session.commit()
    return _out(session, patient)


def _jsonable(values: dict[str, object]) -> dict[str, object]:
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in values.items()}


def add_identifier(
    session: Session,
    principal: Principal,
    crypto: FieldCrypto,
    patient_id: uuid.UUID,
    body: IdentifierIn,
) -> IdentifierOut:
    org_id = _org(principal)
    patient = _get(session, patient_id)
    index = crypto.blind_index(body.value, context=_ident_context(body.system))
    older = crypto.blind_indexes(body.value, context=_ident_context(body.system))
    if session.scalar(
        select(PatientIdentifier.id).where(
            PatientIdentifier.system == body.system, PatientIdentifier.value_index.in_(older)
        )
    ):
        raise Conflict("This identifier is already registered to a patient")
    ident = PatientIdentifier(
        organisation_id=org_id,
        patient_id=patient.id,
        system=body.system,
        value_ciphertext=crypto.encrypt(body.value, context=_ident_context(body.system)),
        value_index=index,
        display_hint=_hint(body.system, body.value),
    )
    session.add(ident)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise Conflict("This identifier is already registered to a patient") from exc
    record_audit(
        session,
        principal.meta,
        org_id=org_id,
        actor_user_id=principal.user_id,
        action="IDENTIFIER_ADDED",
        resource_type="patient",
        resource_id=patient.id,
        after={"system": body.system},
    )
    session.commit()
    return IdentifierOut(
        id=ident.id, system=ident.system, masked=ident.display_hint, verified=False
    )


def reveal_identifier(
    session: Session,
    principal: Principal,
    crypto: FieldCrypto,
    patient_id: uuid.UUID,
    identifier_id: uuid.UUID,
) -> RevealedIdentifier:
    ident = session.scalar(
        select(PatientIdentifier).where(
            PatientIdentifier.id == identifier_id, PatientIdentifier.patient_id == patient_id
        )
    )
    if ident is None:
        raise NotFound("Identifier not found")
    record_audit(
        session,
        principal.meta,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        action="IDENTIFIER_VIEWED",
        resource_type="patient",
        resource_id=patient_id,
        after={"system": ident.system},
    )
    session.commit()
    value = crypto.decrypt(ident.value_ciphertext, context=_ident_context(ident.system))
    return RevealedIdentifier(id=ident.id, system=ident.system, value=value)


def timeline(
    session: Session, principal: Principal, patient_id: uuid.UUID, limit: int, offset: int
) -> list[TimelineEvent]:
    _get(session, patient_id)
    rows = session.scalars(
        select(ClinicalEvent)
        .where(ClinicalEvent.patient_id == patient_id)
        .order_by(ClinicalEvent.occurred_at.desc(), ClinicalEvent.id)
        .limit(limit)
        .offset(offset)
    ).all()
    record_audit(
        session,
        principal.meta,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        action="PATIENT_TIMELINE_VIEWED",
        resource_type="patient",
        resource_id=patient_id,
    )
    session.commit()
    return [
        TimelineEvent(
            id=e.id,
            event_type=e.event_type,
            aggregate_type=e.aggregate_type,
            aggregate_id=e.aggregate_id,
            occurred_at=e.occurred_at.isoformat(),
            actor_user_id=e.actor_user_id,
            payload=e.payload,
        )
        for e in rows
    ]
