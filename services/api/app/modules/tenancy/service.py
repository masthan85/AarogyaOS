import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import Conflict, NotFound
from app.modules.audit.service import record_audit
from app.modules.identity.service import create_org_admin
from app.modules.tenancy.models import Department, Facility, Organisation
from app.modules.tenancy.schemas import (
    DepartmentCreate,
    FacilityCreate,
    FacilityUpdate,
    OrganisationCreate,
)


def create_organisation(
    session: Session, principal: Principal, body: OrganisationCreate
) -> Organisation:
    org = Organisation(name=body.name.strip(), slug=body.slug)
    session.add(org)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise Conflict("Organisation slug already in use") from exc
    create_org_admin(
        session,
        org.id,
        principal.user_id,
        principal.meta,
        email=body.admin_email,
        full_name=body.admin_full_name,
        password=body.admin_password,
    )
    record_audit(
        session,
        principal.meta,
        org_id=org.id,
        actor_user_id=principal.user_id,
        action="ORGANISATION_CREATED",
        resource_type="organisation",
        resource_id=org.id,
        after={"name": org.name, "slug": org.slug},
    )
    session.commit()
    return org


def list_organisations(session: Session) -> list[Organisation]:
    return list(session.scalars(select(Organisation).order_by(Organisation.name)))


def current_organisation(session: Session, principal: Principal) -> Organisation:
    org = session.get(Organisation, principal.org_id)
    if org is None:
        raise NotFound("Organisation not found")
    return org


def create_facility(session: Session, principal: Principal, body: FacilityCreate) -> Facility:
    assert principal.org_id is not None
    facility = Facility(
        organisation_id=principal.org_id,
        name=body.name.strip(),
        code=body.code,
        kind=body.kind,
        address=body.address,
        timezone=body.timezone,
    )
    session.add(facility)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise Conflict("A facility with this code already exists") from exc
    record_audit(
        session,
        principal.meta,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        action="FACILITY_CREATED",
        resource_type="facility",
        resource_id=facility.id,
        after={"name": facility.name, "code": facility.code},
    )
    session.commit()
    return facility


def list_facilities(session: Session, principal: Principal) -> list[Facility]:
    return list(
        session.scalars(
            select(Facility)
            .where(Facility.organisation_id == principal.org_id)
            .order_by(Facility.name)
        )
    )


def get_facility(session: Session, principal: Principal, facility_id: uuid.UUID) -> Facility:
    facility = session.scalar(
        select(Facility).where(
            Facility.id == facility_id, Facility.organisation_id == principal.org_id
        )
    )
    if facility is None:
        raise NotFound("Facility not found")
    return facility


def update_facility(
    session: Session, principal: Principal, facility_id: uuid.UUID, body: FacilityUpdate
) -> Facility:
    facility = get_facility(session, principal, facility_id)
    changes = body.model_dump(exclude_unset=True)
    before = {k: getattr(facility, k) for k in changes}
    for key, value in changes.items():
        setattr(facility, key, value)
    record_audit(
        session,
        principal.meta,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        action="FACILITY_UPDATED",
        resource_type="facility",
        resource_id=facility.id,
        before=before,
        after=changes,
    )
    session.commit()
    return facility


def create_department(session: Session, principal: Principal, body: DepartmentCreate) -> Department:
    assert principal.org_id is not None
    get_facility(session, principal, body.facility_id)  # 404 if it belongs to another tenant
    dept = Department(
        organisation_id=principal.org_id,
        facility_id=body.facility_id,
        name=body.name.strip(),
        specialty=body.specialty,
    )
    session.add(dept)
    session.flush()
    record_audit(
        session,
        principal.meta,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        action="DEPARTMENT_CREATED",
        resource_type="department",
        resource_id=dept.id,
        after={"name": dept.name, "facility_id": str(dept.facility_id)},
    )
    session.commit()
    return dept


def list_departments(
    session: Session, principal: Principal, facility_id: uuid.UUID | None
) -> list[Department]:
    stmt = select(Department).where(Department.organisation_id == principal.org_id)
    if facility_id:
        stmt = stmt.where(Department.facility_id == facility_id)
    return list(session.scalars(stmt.order_by(Department.name)))
