"""Price list, GSTIN setting, end-of-day cash closing and insurance claim tracking."""

import re
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.context import Principal
from app.core.errors import Conflict, NotFound
from app.modules.audit.service import record_audit
from app.modules.billing import service
from app.modules.billing.models import (
    MAX_PAISE,
    BillingSettings,
    CashClosing,
    InsuranceClaim,
    Invoice,
    Payment,
    Refund,
    ServicePrice,
)

IST = ZoneInfo("Asia/Kolkata")
# Shape of a GSTIN (15 characters). The check character is not verified here.
GSTIN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
METHODS = ("CASH", "UPI", "CARD", "INSURER", "OTHER")


def _org(principal: Principal) -> uuid.UUID:
    assert principal.org_id is not None
    return principal.org_id


def _audit(session: Session, principal: Principal, action: str, kind: str, rid: uuid.UUID) -> None:
    record_audit(
        session,
        principal.meta,
        org_id=_org(principal),
        actor_user_id=principal.user_id,
        action=action,
        resource_type=kind,
        resource_id=rid,
    )


# ---- settings ------------------------------------------------------------------------


class SettingsIO(BaseModel):
    gstin: str | None = Field(default=None, max_length=15)
    legal_name: str | None = Field(default=None, max_length=200)

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip().upper()
        if not GSTIN.match(v):
            raise ValueError(
                "That is not in the shape of a GSTIN (15 characters, e.g. 29ABCDE1234F1Z5)"
            )
        return v

    @field_validator("legal_name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return v.strip() or None if v else None


def get_settings(session: Session, principal: Principal) -> SettingsIO:
    row = session.get(BillingSettings, _org(principal))
    return SettingsIO(gstin=row.gstin if row else None, legal_name=row.legal_name if row else None)


def put_settings(session: Session, principal: Principal, body: SettingsIO) -> SettingsIO:
    row = session.get(BillingSettings, _org(principal))
    if row is None:
        row = BillingSettings(organisation_id=_org(principal))
        session.add(row)
    row.gstin, row.legal_name = body.gstin, body.legal_name
    row.updated_at = datetime.now(UTC)
    _audit(session, principal, "BILLING_SETTINGS_CHANGED", "billing_settings", _org(principal))
    session.commit()
    return body


# ---- price list ----------------------------------------------------------------------


class PriceIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    price_paise: int = Field(ge=0, le=MAX_PAISE)
    tax_rate_bp: int = Field(default=0, ge=0, le=2800)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name the service")
        return v


class PriceEdit(BaseModel):
    price_paise: int | None = Field(default=None, ge=0, le=MAX_PAISE)
    tax_rate_bp: int | None = Field(default=None, ge=0, le=2800)
    active: bool | None = None


class PriceOut(BaseModel):
    id: uuid.UUID
    name: str
    price_paise: int
    tax_rate_bp: int
    active: bool


def _price_out(p: ServicePrice) -> PriceOut:
    return PriceOut(
        id=p.id, name=p.name, price_paise=p.price_paise, tax_rate_bp=p.tax_rate_bp, active=p.active
    )


def list_prices(session: Session, *, include_inactive: bool = False) -> list[PriceOut]:
    stmt = select(ServicePrice).order_by(func.lower(ServicePrice.name))
    if not include_inactive:
        stmt = stmt.where(ServicePrice.active.is_(True))
    return [_price_out(p) for p in session.scalars(stmt)]


def add_price(session: Session, principal: Principal, body: PriceIn) -> PriceOut:
    row = ServicePrice(
        organisation_id=_org(principal),
        name=body.name,
        price_paise=body.price_paise,
        tax_rate_bp=body.tax_rate_bp,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise Conflict("That service is already on the price list") from None
    _audit(session, principal, "PRICE_ADDED", "service_prices", row.id)
    session.commit()
    return _price_out(row)


def edit_price(
    session: Session, principal: Principal, price_id: uuid.UUID, body: PriceEdit
) -> PriceOut:
    row = session.get(ServicePrice, price_id)
    if row is None:
        raise NotFound("Service not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(row, key, value)
    _audit(session, principal, "PRICE_CHANGED", "service_prices", row.id)
    session.commit()
    return _price_out(row)


# ---- end of day ----------------------------------------------------------------------


class MethodTotal(BaseModel):
    method: str
    received_paise: int
    refunded_paise: int
    net_paise: int


class DayClosingOut(BaseModel):
    expected_cash_paise: int
    counted_cash_paise: int
    difference_paise: int
    note: str | None
    closed_at: datetime


class DaySummary(BaseModel):
    business_date: date
    by_method: list[MethodTotal]
    net_paise: int
    expected_cash_paise: int
    closing: DayClosingOut | None


class CloseIn(BaseModel):
    business_date: date
    counted_cash_paise: int = Field(ge=0, le=MAX_PAISE)
    note: str | None = Field(default=None, max_length=300)


def _bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=IST)
    return start, start + timedelta(days=1)


def _closing_out(c: CashClosing) -> DayClosingOut:
    return DayClosingOut(
        expected_cash_paise=c.expected_cash_paise,
        counted_cash_paise=c.counted_cash_paise,
        difference_paise=c.counted_cash_paise - c.expected_cash_paise,
        note=c.note,
        closed_at=c.closed_at,
    )


def day_summary(session: Session, day: date) -> DaySummary:
    start, end = _bounds(day)
    paid: dict[str, int] = {
        str(r[0]): int(r[1])
        for r in session.execute(
            select(Payment.method, func.sum(Payment.amount_paise))
            .where(Payment.received_at >= start, Payment.received_at < end)
            .group_by(Payment.method)
        ).all()
    }
    back: dict[str, int] = {
        str(r[0]): int(r[1])
        for r in session.execute(
            select(Refund.method, func.sum(Refund.amount_paise))
            .where(Refund.refunded_at >= start, Refund.refunded_at < end)
            .group_by(Refund.method)
        ).all()
    }
    rows = [
        MethodTotal(
            method=m,
            received_paise=int(paid.get(m, 0)),
            refunded_paise=int(back.get(m, 0)),
            net_paise=int(paid.get(m, 0)) - int(back.get(m, 0)),
        )
        for m in METHODS
        if paid.get(m) or back.get(m)
    ]
    closing = session.scalar(select(CashClosing).where(CashClosing.business_date == day))
    cash = next((r.net_paise for r in rows if r.method == "CASH"), 0)
    return DaySummary(
        business_date=day,
        by_method=rows,
        net_paise=sum(r.net_paise for r in rows),
        expected_cash_paise=cash,
        closing=_closing_out(closing) if closing else None,
    )


def close_day(session: Session, principal: Principal, body: CloseIn) -> DaySummary:
    if body.business_date > datetime.now(IST).date():
        raise Conflict("A day cannot be closed before it has happened")
    summary = day_summary(session, body.business_date)
    if summary.closing is not None:
        raise Conflict("This day has already been closed")
    row = CashClosing(
        organisation_id=_org(principal),
        business_date=body.business_date,
        expected_cash_paise=summary.expected_cash_paise,
        counted_cash_paise=body.counted_cash_paise,
        note=body.note.strip() if body.note and body.note.strip() else None,
        closed_by=principal.user_id,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise Conflict("This day has already been closed") from None
    _audit(session, principal, "CASH_DAY_CLOSED", "cash_closings", row.id)
    session.commit()
    return day_summary(session, body.business_date)


# ---- insurance claims ----------------------------------------------------------------

ClaimStatus = Literal["SUBMITTED", "APPROVED", "PART_APPROVED", "REJECTED", "SETTLED"]
_FINAL = {"REJECTED", "SETTLED"}


class ClaimIn(BaseModel):
    insurer: str = Field(min_length=2, max_length=120)
    policy_number: str | None = Field(default=None, max_length=60)
    claim_reference: str | None = Field(default=None, max_length=60)
    claimed_paise: int = Field(gt=0, le=MAX_PAISE)
    note: str | None = Field(default=None, max_length=300)


class ClaimUpdate(BaseModel):
    status: ClaimStatus | None = None
    approved_paise: int | None = Field(default=None, ge=0, le=MAX_PAISE)
    claim_reference: str | None = Field(default=None, max_length=60)
    note: str | None = Field(default=None, max_length=300)


class ClaimOut(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    insurer: str
    policy_number: str | None
    claim_reference: str | None
    claimed_paise: int
    status: str
    approved_paise: int | None
    note: str | None
    created_at: datetime
    updated_at: datetime


def _claim_out(c: InsuranceClaim) -> ClaimOut:
    return ClaimOut.model_validate(c, from_attributes=True)


def list_claims(session: Session, invoice_id: uuid.UUID) -> list[ClaimOut]:
    rows = session.scalars(
        select(InsuranceClaim)
        .where(InsuranceClaim.invoice_id == invoice_id)
        .order_by(InsuranceClaim.created_at)
    )
    return [_claim_out(c) for c in rows]


def add_claim(
    session: Session, principal: Principal, invoice_id: uuid.UUID, body: ClaimIn
) -> ClaimOut:
    inv = session.get(Invoice, invoice_id)
    if inv is None:
        raise NotFound("Invoice not found")
    if inv.status != "ISSUED":
        raise Conflict("A claim can only be made against an issued invoice")
    live = service.get(session, invoice_id).net_paise
    others = sum(c.claimed_paise for c in session.scalars(
        select(InsuranceClaim).where(
            InsuranceClaim.invoice_id == invoice_id, InsuranceClaim.status != "REJECTED"
        )
    ))  # fmt: skip
    if others + body.claimed_paise > live:
        raise Conflict("Claims on this invoice would add up to more than it is worth")
    row = InsuranceClaim(
        organisation_id=inv.organisation_id,
        invoice_id=inv.id,
        insurer=body.insurer.strip(),
        policy_number=body.policy_number,
        claim_reference=body.claim_reference,
        claimed_paise=body.claimed_paise,
        note=body.note,
        created_by=principal.user_id,
    )
    session.add(row)
    session.flush()
    _audit(session, principal, "CLAIM_SUBMITTED", "insurance_claims", row.id)
    session.commit()
    return _claim_out(row)


def update_claim(
    session: Session, principal: Principal, claim_id: uuid.UUID, body: ClaimUpdate
) -> ClaimOut:
    row = session.get(InsuranceClaim, claim_id)
    if row is None:
        raise NotFound("Claim not found")
    if row.status in _FINAL:
        raise Conflict("A rejected or settled claim cannot be changed")
    changes = body.model_dump(exclude_unset=True)
    approved = changes.get("approved_paise", row.approved_paise)
    status = changes.get("status", row.status)
    if approved is not None and approved > row.claimed_paise:
        raise Conflict("The approved amount cannot be more than was claimed")
    if status in ("APPROVED", "PART_APPROVED", "SETTLED") and approved is None:
        raise Conflict("Enter the amount the insurer approved")
    for key, value in changes.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(UTC)
    _audit(session, principal, "CLAIM_UPDATED", "insurance_claims", row.id)
    session.commit()
    return _claim_out(row)
