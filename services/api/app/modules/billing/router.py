import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core.context import Principal
from app.core.deps import TenantDb, require
from app.modules.billing import extras, service
from app.modules.billing.service import (
    CreditNoteIn,
    DraftIn,
    InvoiceOut,
    LinesIn,
    PaymentIn,
    RefundIn,
    ToBillOut,
    VoidIn,
)

router = APIRouter(tags=["billing"])
Reader = Annotated[Principal, Depends(require("billing:read"))]
Writer = Annotated[Principal, Depends(require("billing:write"))]


@router.get("/billing/to-bill", response_model=list[ToBillOut])
def to_bill(db: TenantDb, _: Writer) -> list[ToBillOut]:
    return service.to_bill(db)


@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(
    db: TenantDb,
    _: Reader,
    status: Annotated[str | None, Query(pattern="^(DRAFT|ISSUED|VOID)$")] = None,
    patient_id: uuid.UUID | None = None,
    unpaid: bool = False,
) -> list[InvoiceOut]:
    return service.list_invoices(db, status=status, patient_id=patient_id, unpaid=unpaid)


@router.post("/invoices", response_model=InvoiceOut, status_code=201)
def create_invoice(body: DraftIn, db: TenantDb, principal: Writer) -> InvoiceOut:
    return service.create_draft(db, principal, body)


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: uuid.UUID, db: TenantDb, _: Reader) -> InvoiceOut:
    return service.get(db, invoice_id)


@router.put("/invoices/{invoice_id}/lines", response_model=InvoiceOut)
def set_lines(invoice_id: uuid.UUID, body: LinesIn, db: TenantDb, principal: Writer) -> InvoiceOut:
    return service.set_lines(db, principal, invoice_id, body)


@router.post("/invoices/{invoice_id}/issue", response_model=InvoiceOut)
def issue_invoice(invoice_id: uuid.UUID, db: TenantDb, principal: Writer) -> InvoiceOut:
    return service.issue(db, principal, invoice_id)


@router.post("/invoices/{invoice_id}/payments", response_model=InvoiceOut, status_code=201)
def pay(invoice_id: uuid.UUID, body: PaymentIn, db: TenantDb, principal: Writer) -> InvoiceOut:
    return service.record_payment(db, principal, invoice_id, body)


@router.post("/invoices/{invoice_id}/void", response_model=InvoiceOut | None)
def void_invoice(
    invoice_id: uuid.UUID, body: VoidIn, db: TenantDb, principal: Writer, response: Response
) -> InvoiceOut | None:
    result = service.void(db, principal, invoice_id, body)
    if result is None:
        response.status_code = 200
    return result


# ---- adjustments, claims, price list, end of day -------------------------------------

Adjuster = Annotated[Principal, Depends(require("billing:adjust"))]
Manager = Annotated[Principal, Depends(require("billing:manage"))]


@router.post("/invoices/{invoice_id}/credit-notes", response_model=InvoiceOut, status_code=201)
def credit_note(
    invoice_id: uuid.UUID, body: CreditNoteIn, db: TenantDb, principal: Adjuster
) -> InvoiceOut:
    return service.add_credit_note(db, principal, invoice_id, body)


@router.post("/invoices/{invoice_id}/refunds", response_model=InvoiceOut, status_code=201)
def refund(invoice_id: uuid.UUID, body: RefundIn, db: TenantDb, principal: Adjuster) -> InvoiceOut:
    return service.add_refund(db, principal, invoice_id, body)


@router.get("/invoices/{invoice_id}/claims", response_model=list[extras.ClaimOut])
def claims(invoice_id: uuid.UUID, db: TenantDb, _: Reader) -> list[extras.ClaimOut]:
    return extras.list_claims(db, invoice_id)


@router.post("/invoices/{invoice_id}/claims", response_model=extras.ClaimOut, status_code=201)
def new_claim(
    invoice_id: uuid.UUID, body: extras.ClaimIn, db: TenantDb, principal: Adjuster
) -> extras.ClaimOut:
    return extras.add_claim(db, principal, invoice_id, body)


@router.put("/claims/{claim_id}", response_model=extras.ClaimOut)
def change_claim(
    claim_id: uuid.UUID, body: extras.ClaimUpdate, db: TenantDb, principal: Adjuster
) -> extras.ClaimOut:
    return extras.update_claim(db, principal, claim_id, body)


@router.get("/billing/settings", response_model=extras.SettingsIO)
def get_settings(db: TenantDb, principal: Reader) -> extras.SettingsIO:
    return extras.get_settings(db, principal)


@router.put("/billing/settings", response_model=extras.SettingsIO)
def put_settings(body: extras.SettingsIO, db: TenantDb, principal: Manager) -> extras.SettingsIO:
    return extras.put_settings(db, principal, body)


@router.get("/billing/prices", response_model=list[extras.PriceOut])
def prices(db: TenantDb, _: Reader, all: bool = False) -> list[extras.PriceOut]:
    return extras.list_prices(db, include_inactive=all)


@router.post("/billing/prices", response_model=extras.PriceOut, status_code=201)
def add_price(body: extras.PriceIn, db: TenantDb, principal: Manager) -> extras.PriceOut:
    return extras.add_price(db, principal, body)


@router.put("/billing/prices/{price_id}", response_model=extras.PriceOut)
def edit_price(
    price_id: uuid.UUID, body: extras.PriceEdit, db: TenantDb, principal: Manager
) -> extras.PriceOut:
    return extras.edit_price(db, principal, price_id, body)


@router.get("/billing/day", response_model=extras.DaySummary)
def day(db: TenantDb, _: Writer, on: date) -> extras.DaySummary:
    return extras.day_summary(db, on)


@router.post("/billing/day/close", response_model=extras.DaySummary, status_code=201)
def close_day(body: extras.CloseIn, db: TenantDb, principal: Writer) -> extras.DaySummary:
    return extras.close_day(db, principal, body)
