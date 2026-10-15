"""Note templates: built-in layouts plus the organisation's own.

A section names the note type it is saved as and the heading and hint a doctor sees. Nothing in a
template is pre-filled, so choosing one can never put words in a record."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import NotFound
from app.modules.audit.service import record_audit
from app.modules.templates.models import NoteTemplate

# Only the types a doctor writes through the notes panel. Triage notes belong to nurses.
SectionType = Literal[
    "HPI", "PAST_HISTORY", "FAMILY_HISTORY", "SOCIAL_HISTORY", "EXAMINATION", "ASSESSMENT", "PLAN"
]


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note_type: SectionType
    title: str = Field(min_length=1, max_length=60)
    hint: str = Field(default="", max_length=160)


class TemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=80)
    specialty: str | None = Field(default=None, max_length=80)
    sections: list[Section] = Field(min_length=1, max_length=12)
    active: bool = True

    @field_validator("sections")
    @classmethod
    def _unique_titles(cls, v: list[Section]) -> list[Section]:
        if len({s.title.casefold() for s in v}) != len(v):
            raise ValueError("Section titles must be different from each other")
        return v


class TemplateOut(BaseModel):
    id: str
    name: str
    specialty: str | None
    sections: list[Section]
    active: bool
    builtin: bool


def _builtin(key: str, name: str, sections: list[Section]) -> TemplateOut:
    return TemplateOut(
        id=f"builtin:{key}", name=name, specialty=None, sections=sections, active=True, builtin=True
    )


BUILTIN: list[TemplateOut] = [
    _builtin(
        "consultation",
        "General consultation",
        [
            Section(note_type="HPI", title="History", hint="What the patient reports"),
            Section(note_type="EXAMINATION", title="Examination", hint="What you found"),
            Section(note_type="ASSESSMENT", title="Assessment", hint="Your clinical impression"),
            Section(note_type="PLAN", title="Plan", hint="What happens next"),
        ],
    ),
    _builtin(
        "follow-up",
        "Follow-up review",
        [
            Section(note_type="HPI", title="Since the last visit"),
            Section(note_type="EXAMINATION", title="Examination"),
            Section(note_type="ASSESSMENT", title="Progress"),
            Section(note_type="PLAN", title="Plan"),
        ],
    ),
]


def _out(t: NoteTemplate) -> TemplateOut:
    return TemplateOut(
        id=str(t.id),
        name=t.name,
        specialty=t.specialty,
        sections=[Section.model_validate(s) for s in t.sections],
        active=t.active,
        builtin=False,
    )


def list_templates(session: Session, *, include_inactive: bool = False) -> list[TemplateOut]:
    rows = session.scalars(select(NoteTemplate).order_by(NoteTemplate.name))
    own = [_out(t) for t in rows if include_inactive or t.active]
    return [*BUILTIN, *own]


def _get(session: Session, template_id: uuid.UUID) -> NoteTemplate:
    t = session.get(NoteTemplate, template_id)
    if t is None:
        raise NotFound("Template not found")
    return t


def _audit(session: Session, principal: Principal, action: str, t: NoteTemplate) -> None:
    assert principal.org_id is not None
    record_audit(
        session,
        principal.meta,
        org_id=principal.org_id,
        actor_user_id=principal.user_id,
        action=action,
        resource_type="note_template",
        resource_id=t.id,
        after={"name": t.name},
    )


def create(session: Session, principal: Principal, body: TemplateIn) -> TemplateOut:
    assert principal.org_id is not None
    t = NoteTemplate(
        organisation_id=principal.org_id,
        name=body.name,
        specialty=body.specialty,
        sections=[s.model_dump() for s in body.sections],
        active=body.active,
        created_by=principal.user_id,
    )
    session.add(t)
    session.flush()
    _audit(session, principal, "NOTE_TEMPLATE_CREATED", t)
    session.commit()
    return _out(t)


def update(
    session: Session, principal: Principal, template_id: uuid.UUID, body: TemplateIn
) -> TemplateOut:
    t = _get(session, template_id)
    t.name, t.specialty, t.active = body.name, body.specialty, body.active
    t.sections = [s.model_dump() for s in body.sections]
    _audit(session, principal, "NOTE_TEMPLATE_UPDATED", t)
    session.commit()
    return _out(t)


__all__ = ["BUILTIN", "Section", "TemplateIn", "TemplateOut", "create", "list_templates", "update"]
