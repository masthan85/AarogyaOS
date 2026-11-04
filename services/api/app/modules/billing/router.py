import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core.context import Principal
from app.core.deps import TenantDb, require
from app.modules.billing import service
from app.modules.billing.service import (
    DraftIn,
    InvoiceOut,
    LinesIn,
    PaymentIn,
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
