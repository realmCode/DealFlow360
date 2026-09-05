"""Billing endpoints: schedules (P0), invoices and payments (P1)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.dependencies import DbSession, FinanceUser, InternalUser
from app.enums import (
    BillingScheduleStatus,
    BillingType,
    CreditNoteStatus,
    InvoiceStatus,
    PaymentStatus,
)
from app.errors import BusinessRuleError, ConflictError, NotFoundError
from app.events import EventType
from app.models.billing_schedule import BillingSchedule
from app.models.credit_note import CreditNote
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.sales_order import SalesOrder
from app.schemas.billing import (
    BillingScheduleRead,
    BillingSummary,
    InvoiceCreate,
    InvoiceRead,
    InvoiceVoidRequest,
    PaymentCreate,
    PaymentRead,
    ProrationPreview,
)
from app.schemas.subscription import (
    CreditNoteRead,
    CreditNoteRefundRequest,
    CreditNoteVoidRequest,
    SubscriptionCancelRequest,
    SubscriptionChangeRequest,
    SubscriptionChangeResponse,
)
from app.services.audit_service import AuditService
from app.services.billing_service import BillingService
from app.services.commercial_engine import money
from app.services.order_service import OrderService
from app.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/billing", tags=["billing"])


def _credit_note_read(note: CreditNote) -> CreditNoteRead:
    return CreditNoteRead(
        id=note.id,
        created_at=note.created_at,
        updated_at=note.updated_at,
        credit_note_number=note.credit_note_number,
        sales_order_id=note.sales_order_id,
        invoice_id=note.invoice_id,
        billing_schedule_id=note.billing_schedule_id,
        customer_organization_id=note.customer_organization_id,
        status=note.status,
        reason=note.reason,
        reason_note=note.reason_note,
        currency=note.currency,
        subtotal=note.subtotal,
        tax_amount=note.tax_amount,
        total_amount=note.total_amount,
        amount_refunded=note.amount_refunded,
        amount_outstanding=note.amount_outstanding,
        issue_date=note.issue_date,
        issued_by_user_id=note.issued_by_user_id,
        voided_at=note.voided_at,
        detail=note.detail or {},
    )


def _invoice_read(invoice: Invoice) -> InvoiceRead:
    # Overdue is derived rather than stored: there is no background scheduler,
    # so a stored flag would be stale the moment a due date passed.
    unsettled = invoice.status in (
        InvoiceStatus.ISSUED,
        InvoiceStatus.PARTIALLY_PAID,
    )
    today = datetime.now(UTC).date()
    overdue = unsettled and invoice.due_date < today
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
        is_overdue=overdue,
        days_overdue=(today - invoice.due_date).days if overdue else 0,
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
    payload: InvoiceCreate, user: FinanceUser, db: DbSession
) -> InvoiceRead:
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
    user: FinanceUser,
    db: DbSession,
) -> PaymentRead:
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
    await AuditService.emit(
        db,
        EventType.PAYMENT_RECORDED,
        organization_id=user.organization_id,
        entity_type="payment",
        entity_id=payment.id,
        actor=user,
        payload={
            "payment_number": payment.payment_number,
            "invoice_number": invoice.invoice_number,
            "amount": str(money(payload.amount)),
            "method": payload.method.value,
            "invoice_status": invoice.status.value,
            "amount_paid": str(money(invoice.amount_paid)),
            "amount_due": str(money(invoice.amount_due)),
        },
    )
    await db.commit()
    return PaymentRead.model_validate(payment)


@router.post(
    "/invoices/{invoice_id}/void",
    response_model=InvoiceRead,
    summary="Void an invoice issued in error",
)
async def void_invoice(
    invoice_id: uuid.UUID,
    payload: InvoiceVoidRequest,
    user: FinanceUser,
    db: DbSession,
) -> InvoiceRead:
    """``InvoiceStatus.VOID`` was previously read but never set, so a
    mis-issued invoice could not be cancelled."""
    invoice = await db.get(Invoice, invoice_id)
    if invoice is None or invoice.organization_id != user.organization_id:
        raise NotFoundError("Invoice not found.")
    if invoice.status is InvoiceStatus.VOID:
        raise ConflictError("This invoice is already void.", code="INVOICE_VOID")
    if Decimal(invoice.amount_paid) > Decimal("0"):
        raise ConflictError(
            "A part-paid invoice cannot be voided. Issue a credit note instead.",
            code="INVOICE_PART_PAID",
            details={"amount_paid": str(money(invoice.amount_paid))},
        )

    invoice.status = InvoiceStatus.VOID
    schedule = (
        await db.get(BillingSchedule, invoice.billing_schedule_id)
        if invoice.billing_schedule_id
        else None
    )
    if schedule is not None and schedule.status is BillingScheduleStatus.INVOICED:
        # Return the schedule to billable so it can be re-invoiced correctly.
        schedule.status = BillingScheduleStatus.SCHEDULED
    await db.flush()
    await AuditService.emit(
        db,
        EventType.INVOICE_VOIDED,
        organization_id=user.organization_id,
        entity_type="invoice",
        entity_id=invoice.id,
        actor=user,
        payload={
            "invoice_number": invoice.invoice_number,
            "reason": payload.reason,
        },
    )
    await db.commit()
    return _invoice_read(invoice)


# ------------------------------------------- subscription lifecycle (A5/B7)
@router.post(
    "/subscriptions/{schedule_id}/change",
    response_model=SubscriptionChangeResponse,
    summary="Apply a mid-cycle quantity or interval change with proration",
)
async def change_subscription(
    schedule_id: uuid.UUID,
    payload: SubscriptionChangeRequest,
    user: FinanceUser,
    db: DbSession,
) -> SubscriptionChangeResponse:
    """PDF A5/B7 — "Handles mid cycle proration when quantity changes".

    The proration maths already existed as a read-only preview; this applies
    it, regenerates the remaining periods, and leaves invoiced history alone.
    """
    schedule = await SubscriptionService.get_schedule(
        db, schedule_id, user.organization_id
    )
    result = await SubscriptionService.change(
        db,
        schedule=schedule,
        actor=user,
        new_quantity=payload.new_quantity,
        new_interval=payload.new_interval,
        effective_date=payload.effective_date,
        reason=payload.reason,
    )
    await db.commit()
    return SubscriptionChangeResponse.model_validate(result.as_dict())


@router.post(
    "/subscriptions/{schedule_id}/cancel",
    response_model=SubscriptionChangeResponse,
    summary="Cancel a subscription, crediting the unused portion",
)
async def cancel_subscription(
    schedule_id: uuid.UUID,
    payload: SubscriptionCancelRequest,
    user: FinanceUser,
    db: DbSession,
) -> SubscriptionChangeResponse:
    """PDF A5/B7 — cancellation with "automatic partial refund or credit note"."""
    schedule = await SubscriptionService.get_schedule(
        db, schedule_id, user.organization_id
    )
    result = await SubscriptionService.cancel(
        db,
        schedule=schedule,
        actor=user,
        effective_date=payload.effective_date,
        reason=payload.reason,
    )
    await db.commit()
    return SubscriptionChangeResponse.model_validate(result.as_dict())


# ----------------------------------------------------------- credit notes
@router.get(
    "/credit-notes",
    response_model=list[CreditNoteRead],
    summary="List credit notes",
)
async def list_credit_notes(
    user: InternalUser,
    db: DbSession,
    sales_order_id: uuid.UUID | None = Query(default=None),
    status_: CreditNoteStatus | None = Query(default=None, alias="status"),
) -> list[CreditNoteRead]:
    stmt = select(CreditNote).where(
        CreditNote.organization_id == user.organization_id
    )
    if sales_order_id is not None:
        stmt = stmt.where(CreditNote.sales_order_id == sales_order_id)
    if status_ is not None:
        stmt = stmt.where(CreditNote.status == status_)
    rows = (await db.execute(stmt.order_by(CreditNote.issue_date.desc()))).scalars()
    return [_credit_note_read(n) for n in rows]


@router.get(
    "/credit-notes/{credit_note_id}",
    response_model=CreditNoteRead,
    summary="Get one credit note, including its proration arithmetic",
)
async def get_credit_note(
    credit_note_id: uuid.UUID, user: InternalUser, db: DbSession
) -> CreditNoteRead:
    note = await db.get(CreditNote, credit_note_id)
    if note is None or note.organization_id != user.organization_id:
        raise NotFoundError("Credit note not found.")
    return _credit_note_read(note)


@router.post(
    "/credit-notes/{credit_note_id}/refund",
    response_model=CreditNoteRead,
    summary="Record cash refunded against a credit note",
)
async def refund_credit_note(
    credit_note_id: uuid.UUID,
    payload: CreditNoteRefundRequest,
    user: FinanceUser,
    db: DbSession,
) -> CreditNoteRead:
    """This is what makes ``PaymentStatus.REFUNDED`` reachable — PDF A5's
    "partial refund" requirement."""
    note = await db.get(CreditNote, credit_note_id)
    if note is None or note.organization_id != user.organization_id:
        raise NotFoundError("Credit note not found.")
    await SubscriptionService.refund_credit_note(
        db, note=note, actor=user, amount=payload.amount
    )
    await db.commit()
    return _credit_note_read(note)


@router.post(
    "/credit-notes/{credit_note_id}/void",
    response_model=CreditNoteRead,
    summary="Void a credit note issued in error",
)
async def void_credit_note(
    credit_note_id: uuid.UUID,
    payload: CreditNoteVoidRequest,
    user: FinanceUser,
    db: DbSession,
) -> CreditNoteRead:
    note = await db.get(CreditNote, credit_note_id)
    if note is None or note.organization_id != user.organization_id:
        raise NotFoundError("Credit note not found.")
    await SubscriptionService.void_credit_note(
        db, note=note, actor=user, reason=payload.reason
    )
    await db.commit()
    return _credit_note_read(note)
