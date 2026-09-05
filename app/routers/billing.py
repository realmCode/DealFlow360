"""Billing endpoints: schedules (P0), invoices and payments (P1)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.dependencies import DbSession, InternalUser
from app.enums import (
    BillingScheduleStatus,
    BillingType,
    InvoiceStatus,
    PaymentStatus,
    RoleCode,
)
from app.errors import AuthorizationError, BusinessRuleError, ConflictError, NotFoundError
from app.models.billing_schedule import BillingSchedule
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.sales_order import SalesOrder
from app.schemas.billing import (
    BillingScheduleRead,
    BillingSummary,
    InvoiceCreate,
    InvoiceRead,
    PaymentCreate,
    PaymentRead,
    ProrationPreview,
)
from app.services.billing_service import BillingService
from app.services.commercial_engine import money
from app.services.order_service import OrderService

router = APIRouter(prefix="/billing", tags=["billing"])


def _invoice_read(invoice: Invoice) -> InvoiceRead:
    return InvoiceRead(
        id=invoice.id,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
        invoice_number=invoice.invoice_number,
        sales_order_id=invoice.sales_order_id,
        billing_schedule_id=invoice.billing_schedule_id,
        status=invoice.status,
        currency=invoice.currency,
        subtotal=invoice.subtotal,
        tax_amount=invoice.tax_amount,
        total_amount=invoice.total_amount,
        amount_paid=invoice.amount_paid,
        amount_due=invoice.amount_due,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        paid_at=invoice.paid_at,
    )


@router.get(
    "/schedules",
    response_model=list[BillingScheduleRead],
    summary="Billing schedules — one-time and recurring coexist per order",
)
async def list_schedules(
    user: InternalUser,
    db: DbSession,
    sales_order_id: uuid.UUID | None = Query(default=None),
    billing_type: BillingType | None = Query(default=None),
) -> list[BillingScheduleRead]:
    schedules = await BillingService.list_schedules(
        db,
        organization_id=user.organization_id,
        sales_order_id=sales_order_id,
        billing_type=billing_type,
    )
    return [BillingScheduleRead.model_validate(s) for s in schedules]


@router.get(
    "/orders/{order_id}/summary",
    response_model=BillingSummary,
    summary="One-time vs recurring totals for an order",
)
async def billing_summary(
    order_id: uuid.UUID, user: InternalUser, db: DbSession
) -> BillingSummary:
    order = await OrderService.get_order(db, order_id, user.organization_id)
    return BillingSummary(**await BillingService.summarise(db, order))


@router.get(
    "/proration-preview",
    response_model=ProrationPreview,
    summary="Preview the reusable proration calculation",
)
async def proration_preview(
    user: InternalUser,
    full_period_amount: Decimal = Query(..., gt=0),
    period_start: date = Query(...),
    period_end: date = Query(...),
    billed_from: date = Query(...),
) -> ProrationPreview:
    result = BillingService.prorate(
        full_period_amount=full_period_amount,
        period_start=period_start,
        period_end=period_end,
        billed_from=billed_from,
    )
    return ProrationPreview(
        full_period_amount=result.full_period_amount,
        days_in_period=result.days_in_period,
        days_billed=result.days_billed,
        proration_factor=result.proration_factor,
        prorated_amount=result.prorated_amount,
        explanation=result.explanation,
    )


# ------------------------------------------------------------------- P1
@router.post(
    "/invoices",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Issue an invoice from a billing schedule (P1)",
)
async def create_invoice(
    payload: InvoiceCreate, user: InternalUser, db: DbSession
) -> InvoiceRead:
    if user.role_code not in (RoleCode.FINANCE, RoleCode.ADMIN):
        raise AuthorizationError(
            "Only FINANCE or ADMIN may issue invoices.",
            details={"your_role": user.role_code.value},
        )
    schedule = await db.get(BillingSchedule, payload.billing_schedule_id)
    if schedule is None or schedule.organization_id != user.organization_id:
        raise NotFoundError("Billing schedule not found.")
    if schedule.status is BillingScheduleStatus.INVOICED:
        raise ConflictError(
            "This schedule has already been invoiced.",
            code="SCHEDULE_ALREADY_INVOICED",
        )

    order = await db.get(SalesOrder, schedule.sales_order_id)
    assert order is not None
    count = (
        await db.execute(
            select(func.count())
            .select_from(Invoice)
            .where(Invoice.organization_id == user.organization_id)
        )
    ).scalar_one()

    issue_date = payload.issue_date or datetime.now(UTC).date()
    invoice = Invoice(
        organization_id=user.organization_id,
        invoice_number=f"INV-{int(count) + 1:05d}",
        sales_order_id=order.id,
        billing_schedule_id=schedule.id,
        customer_organization_id=order.customer_organization_id,
        status=InvoiceStatus.ISSUED,
        currency=schedule.currency,
        subtotal=money(schedule.amount),
        tax_amount=money(schedule.tax_amount),
        total_amount=money(schedule.total_amount),
        issue_date=issue_date,
        due_date=max(issue_date, schedule.due_date),
    )
    db.add(invoice)
    schedule.status = BillingScheduleStatus.INVOICED
    await db.flush()
    await db.commit()
    return _invoice_read(invoice)


@router.get("/invoices", response_model=list[InvoiceRead], summary="List invoices (P1)")
async def list_invoices(user: InternalUser, db: DbSession) -> list[InvoiceRead]:
    rows = (
        await db.execute(
            select(Invoice)
            .where(Invoice.organization_id == user.organization_id)
            .order_by(Invoice.issue_date.desc())
        )
    ).scalars()
    return [_invoice_read(i) for i in rows]


@router.post(
    "/invoices/{invoice_id}/payments",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a payment against an invoice (P1)",
)
async def record_payment(
    invoice_id: uuid.UUID,
    payload: PaymentCreate,
    user: InternalUser,
    db: DbSession,
) -> PaymentRead:
    if user.role_code not in (RoleCode.FINANCE, RoleCode.ADMIN):
        raise AuthorizationError(
            "Only FINANCE or ADMIN may record payments.",
            details={"your_role": user.role_code.value},
        )
    invoice = await db.get(Invoice, invoice_id)
    if invoice is None or invoice.organization_id != user.organization_id:
        raise NotFoundError("Invoice not found.")
    if invoice.status is InvoiceStatus.VOID:
        raise ConflictError("Cannot pay a voided invoice.", code="INVOICE_VOID")

    outstanding = invoice.amount_due
    if payload.amount > outstanding:
        raise BusinessRuleError(
            f"Payment of {payload.amount} exceeds the outstanding balance of "
            f"{outstanding}.",
            code="OVERPAYMENT",
            details={"amount_due": str(outstanding)},
        )

    count = (
        await db.execute(
            select(func.count())
            .select_from(Payment)
            .where(Payment.organization_id == user.organization_id)
        )
    ).scalar_one()
    payment = Payment(
        organization_id=user.organization_id,
        payment_number=f"PAY-{int(count) + 1:05d}",
        invoice_id=invoice.id,
        amount=money(payload.amount),
        currency=invoice.currency,
        method=payload.method,
        status=PaymentStatus.SETTLED,
        reference=payload.reference,
        notes=payload.notes,
        recorded_by_user_id=user.id,
    )
    db.add(payment)
    invoice.amount_paid = money(invoice.amount_paid + payload.amount)
    if invoice.amount_paid >= invoice.total_amount:
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = datetime.now(UTC)
        schedule = (
            await db.get(BillingSchedule, invoice.billing_schedule_id)
            if invoice.billing_schedule_id
            else None
        )
        if schedule is not None:
            schedule.status = BillingScheduleStatus.COMPLETED
    else:
        invoice.status = InvoiceStatus.PARTIALLY_PAID
    await db.flush()
    await db.commit()
    return PaymentRead.model_validate(payment)
