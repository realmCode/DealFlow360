"""Subscription lifecycle — PDF A5 and B7.

`BillingService` already knew how to *calculate* proration; what was missing was
anything that *applied* it. The maths was exposed read-only at
`GET /billing/proration-preview`, which made it a calculator rather than a
workflow: nothing could change a subscription quantity mid-term or cancel one.

This module supplies the two operations the PDF names:

    A5/B7  "proration rules for mid cycle quantity or plan changes"
    A5/B7  "cancellation and partial refund rules" + "credit note trigger"

Two invariants shape the implementation.

**Invoiced history is immutable.** A period that has been invoiced represents a
document sent to a customer. Changing it retroactively would destroy the record
of what they were actually billed, so any change to an invoiced period is
refused rather than silently rewritten. Adjustments flow forward, and money
already charged is returned through a credit note.

**Sums stay exact.** `BillingService.split_amount` guarantees the schedules for
a line sum to the line's net amount. Regenerating future periods preserves that
property for the remaining term.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    INTERVAL_MONTHS,
    BillingScheduleStatus,
    BillingType,
    CreditNoteReason,
    CreditNoteStatus,
    InvoiceStatus,
    PaymentStatus,
    RecurringInterval,
    SubscriptionChangeType,
)
from app.errors import BusinessRuleError, ConflictError, NotFoundError
from app.events import EventType
from app.models.billing_schedule import BillingSchedule
from app.models.credit_note import CreditNote
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.sales_order import SalesOrder
from app.models.sales_order_line import SalesOrderLine
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.billing_service import TERMS_DAYS, BillingService, add_months
from app.services.commercial_engine import ZERO, money, pct


@dataclass(slots=True)
class SubscriptionChangeResult:
    change_type: SubscriptionChangeType
    sales_order_line_id: uuid.UUID
    effective_date: date
    periods_kept: int
    periods_regenerated: int
    previous_period_amount: Decimal
    new_period_amount: Decimal
    proration_credit: Decimal
    proration_charge: Decimal
    credit_note_id: uuid.UUID | None
    schedules: list[dict[str, Any]] = field(default_factory=list)
    explanation: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "change_type": self.change_type.value,
            "sales_order_line_id": str(self.sales_order_line_id),
            "effective_date": self.effective_date.isoformat(),
            "periods_kept": self.periods_kept,
            "periods_regenerated": self.periods_regenerated,
            "previous_period_amount": str(self.previous_period_amount),
            "new_period_amount": str(self.new_period_amount),
            "proration_credit": str(self.proration_credit),
            "proration_charge": str(self.proration_charge),
            "credit_note_id": (
                str(self.credit_note_id) if self.credit_note_id else None
            ),
            "schedules": self.schedules,
            "explanation": self.explanation,
        }


class SubscriptionService:
    # ------------------------------------------------------------- loading
    @staticmethod
    async def get_schedule(
        session: AsyncSession, schedule_id: uuid.UUID, organization_id: uuid.UUID
    ) -> BillingSchedule:
        schedule = await session.get(BillingSchedule, schedule_id)
        if schedule is None or schedule.organization_id != organization_id:
            raise NotFoundError("Billing schedule not found.")
        return schedule

    @staticmethod
    def _assert_recurring(schedule: BillingSchedule) -> None:
        if schedule.billing_type is not BillingType.RECURRING:
            raise BusinessRuleError(
                "Only a recurring subscription schedule can be changed or "
                "cancelled. One-time lines are amended by revising the quote.",
                code="SUBSCRIPTION_NOT_RECURRING",
                details={
                    "billing_type": schedule.billing_type.value,
                    "schedule_number": schedule.schedule_number,
                },
            )

    @staticmethod
    async def _line_schedules(
        session: AsyncSession, line_id: uuid.UUID
    ) -> list[BillingSchedule]:
        return list(
            (
                await session.execute(
                    select(BillingSchedule)
                    .where(BillingSchedule.sales_order_line_id == line_id)
                    .order_by(BillingSchedule.period_number)
                )
            ).scalars()
        )

    # ------------------------------------------------------- mid-cycle change
    @classmethod
    async def change(
        cls,
        session: AsyncSession,
        *,
        schedule: BillingSchedule,
        actor: User,
        new_quantity: Decimal | None = None,
        new_interval: RecurringInterval | None = None,
        effective_date: date | None = None,
        reason: str | None = None,
    ) -> SubscriptionChangeResult:
        """Apply a mid-cycle quantity or interval change with real proration."""
        cls._assert_recurring(schedule)

        if new_quantity is None and new_interval is None:
            raise BusinessRuleError(
                "Supply new_quantity and/or new_interval.",
                code="EMPTY_SUBSCRIPTION_CHANGE",
            )

        effective = effective_date or datetime.now(UTC).date()
        if not (schedule.period_start <= effective <= schedule.period_end):
            raise BusinessRuleError(
                "effective_date must fall inside the period being changed "
                f"({schedule.period_start.isoformat()} to "
                f"{schedule.period_end.isoformat()}).",
                code="EFFECTIVE_DATE_OUTSIDE_PERIOD",
                details={
                    "effective_date": effective.isoformat(),
                    "period_start": schedule.period_start.isoformat(),
                    "period_end": schedule.period_end.isoformat(),
                },
            )
        if schedule.status is BillingScheduleStatus.INVOICED:
            raise ConflictError(
                "This period has already been invoiced and cannot be changed. "
                "Cancel and re-issue, or apply the change from the next period.",
                code="PERIOD_ALREADY_INVOICED",
                details={"schedule_number": schedule.schedule_number},
            )
        if schedule.status is BillingScheduleStatus.CANCELLED:
            raise ConflictError(
                "This subscription period is already cancelled.",
                code="SCHEDULE_ALREADY_CANCELLED",
                details={"schedule_number": schedule.schedule_number},
            )

        line = await session.get(SalesOrderLine, schedule.sales_order_line_id)
        if line is None:
            raise NotFoundError("The order line for this schedule no longer exists.")
        order = await session.get(SalesOrder, schedule.sales_order_id)
        if order is None:
            raise NotFoundError("The order for this schedule no longer exists.")

        interval = new_interval or schedule.recurring_interval
        assert interval is not None  # guaranteed by the recurring CHECK constraint
        old_quantity = Decimal(line.quantity)
        quantity = Decimal(new_quantity) if new_quantity is not None else old_quantity
        if quantity <= ZERO:
            raise BusinessRuleError(
                "new_quantity must be greater than zero. To end the "
                "subscription use the cancel endpoint.",
                code="INVALID_SUBSCRIPTION_QUANTITY",
                details={"new_quantity": str(quantity)},
            )

        unit_net = Decimal(line.unit_net_price)
        previous_period_amount = money(schedule.amount)
        months = INTERVAL_MONTHS[interval]
        new_period_amount = money(unit_net * quantity * Decimal(months) / Decimal(
            INTERVAL_MONTHS[schedule.recurring_interval]
            if schedule.recurring_interval
            else months
        ))

        # Split the period being changed: the old rate applies up to the day
        # before the change, the new rate from the change onward.
        old_part = BillingService.prorate(
            full_period_amount=previous_period_amount,
            period_start=schedule.period_start,
            period_end=schedule.period_end,
            billed_from=schedule.period_start,
        )
        remaining = BillingService.prorate(
            full_period_amount=previous_period_amount,
            period_start=schedule.period_start,
            period_end=schedule.period_end,
            billed_from=effective,
        )
        consumed_amount = money(
            old_part.prorated_amount - remaining.prorated_amount
        )
        new_remaining = BillingService.prorate(
            full_period_amount=new_period_amount,
            period_start=schedule.period_start,
            period_end=schedule.period_end,
            billed_from=effective,
        )
        blended_current = money(consumed_amount + new_remaining.prorated_amount)

        proration_credit = ZERO
        proration_charge = ZERO
        delta = money(blended_current - previous_period_amount)
        if delta > ZERO:
            proration_charge = delta
        elif delta < ZERO:
            proration_credit = money(-delta)

        # Rewrite the current period to the blended amount.
        schedule.amount = blended_current
        schedule.total_amount = money(blended_current + Decimal(schedule.tax_amount))
        schedule.is_prorated = True
        schedule.proration_factor = new_remaining.proration_factor
        schedule.status = BillingScheduleStatus.ACTIVE
        schedule.recurring_interval = interval
        schedule.description = (
            f"{line.description} — period {schedule.period_number} "
            f"(changed {effective.isoformat()})"
        )
        schedule.detail = {
            **(schedule.detail or {}),
            "changed_at": datetime.now(UTC).isoformat(),
            "change_effective_date": effective.isoformat(),
            "previous_quantity": str(old_quantity),
            "new_quantity": str(quantity),
            "previous_period_amount": str(previous_period_amount),
            "new_period_amount": str(new_period_amount),
            "consumed_at_old_rate": str(consumed_amount),
            "remaining_at_new_rate": str(new_remaining.prorated_amount),
            "proration_explanation": new_remaining.explanation,
        }

        # Regenerate every later period at the new rate. Invoiced periods are
        # left alone: they are already documents in the customer's hands.
        siblings = await cls._line_schedules(session, line.id)
        regenerated = 0
        for later in siblings:
            if later.period_number <= schedule.period_number:
                continue
            if later.status in (
                BillingScheduleStatus.INVOICED,
                BillingScheduleStatus.COMPLETED,
            ):
                continue
            later.amount = new_period_amount
            later.total_amount = money(
                new_period_amount + Decimal(later.tax_amount)
            )
            later.recurring_interval = interval
            later.detail = {
                **(later.detail or {}),
                "regenerated_from_change": effective.isoformat(),
                "quantity": str(quantity),
            }
            regenerated += 1

        # The line is the source of truth for billing, so it must reflect the
        # new quantity or every future recomputation would undo the change.
        line.quantity = quantity
        if new_quantity is not None:
            line.net_amount = money(unit_net * quantity)
        line.recurring_interval = interval

        credit_note_id: uuid.UUID | None = None
        if proration_credit > ZERO:
            note = await cls._issue_credit_note(
                session,
                order=order,
                schedule=schedule,
                actor=actor,
                amount=proration_credit,
                reason=CreditNoteReason.SUBSCRIPTION_DOWNGRADED,
                reason_note=reason
                or (
                    f"Mid-cycle downgrade of '{line.description}' effective "
                    f"{effective.isoformat()}."
                ),
                detail={
                    "previous_period_amount": str(previous_period_amount),
                    "blended_period_amount": str(blended_current),
                    "proration": new_remaining.explanation,
                },
            )
            credit_note_id = note.id

        await session.flush()

        change_type = (
            SubscriptionChangeType.QUANTITY
            if new_quantity is not None
            else SubscriptionChangeType.INTERVAL
        )
        explanation = (
            f"{line.description} changed from {old_quantity} to {quantity} "
            f"at a {interval.value.lower()} interval, effective "
            f"{effective.isoformat()}. Period {schedule.period_number} is "
            f"prorated to {blended_current} "
            f"({consumed_amount} at the old rate plus "
            f"{new_remaining.prorated_amount} at the new rate), and "
            f"{regenerated} later period(s) were regenerated at "
            f"{new_period_amount}."
        )

        await AuditService.emit(
            session,
            EventType.SUBSCRIPTION_CHANGED,
            organization_id=order.organization_id,
            entity_type="billing_schedule",
            entity_id=schedule.id,
            actor=actor,
            payload={
                "order_number": order.order_number,
                "schedule_number": schedule.schedule_number,
                "change_type": change_type.value,
                "effective_date": effective.isoformat(),
                "previous_quantity": str(old_quantity),
                "new_quantity": str(quantity),
                "interval": interval.value,
                "blended_period_amount": str(blended_current),
                "new_period_amount": str(new_period_amount),
                "proration_credit": str(proration_credit),
                "proration_charge": str(proration_charge),
                "periods_regenerated": regenerated,
            },
        )

        return SubscriptionChangeResult(
            change_type=change_type,
            sales_order_line_id=line.id,
            effective_date=effective,
            periods_kept=schedule.period_number,
            periods_regenerated=regenerated,
            previous_period_amount=previous_period_amount,
            new_period_amount=new_period_amount,
            proration_credit=proration_credit,
            proration_charge=proration_charge,
            credit_note_id=credit_note_id,
            schedules=[
                {
                    "schedule_number": s.schedule_number,
                    "period_number": s.period_number,
                    "status": s.status.value,
                    "amount": str(money(s.amount)),
                    "period_start": s.period_start.isoformat(),
                    "period_end": s.period_end.isoformat(),
                }
                for s in await cls._line_schedules(session, line.id)
            ],
            explanation=explanation,
        )

    # ------------------------------------------------------------- cancel
    @classmethod
    async def cancel(
        cls,
        session: AsyncSession,
        *,
        schedule: BillingSchedule,
        actor: User,
        effective_date: date | None = None,
        reason: str | None = None,
    ) -> SubscriptionChangeResult:
        """Cancel a subscription, crediting the unused portion.

        The unused part of the current period is refundable; consumed days are
        not. Every later period is cancelled outright.
        """
        cls._assert_recurring(schedule)

        if schedule.status is BillingScheduleStatus.CANCELLED:
            raise ConflictError(
                "This subscription is already cancelled.",
                code="SCHEDULE_ALREADY_CANCELLED",
                details={"schedule_number": schedule.schedule_number},
            )

        effective = effective_date or datetime.now(UTC).date()
        # Cancelling before the period opens means nothing was consumed;
        # clamp rather than reject so an early cancellation is not a 400.
        if effective < schedule.period_start:
            effective = schedule.period_start
        if effective > schedule.period_end:
            raise BusinessRuleError(
                "effective_date is after the end of this period. Cancel the "
                "period that contains the date instead.",
                code="EFFECTIVE_DATE_OUTSIDE_PERIOD",
                details={
                    "effective_date": effective.isoformat(),
                    "period_end": schedule.period_end.isoformat(),
                },
            )

        line = await session.get(SalesOrderLine, schedule.sales_order_line_id)
        order = await session.get(SalesOrder, schedule.sales_order_id)
        if line is None or order is None:
            raise NotFoundError("The order for this schedule no longer exists.")

        period_amount = money(schedule.amount)
        # Unused portion = the part billed from the effective date onward.
        unused = BillingService.prorate(
            full_period_amount=period_amount,
            period_start=schedule.period_start,
            period_end=schedule.period_end,
            billed_from=effective,
        )
        consumed = money(period_amount - unused.prorated_amount)

        siblings = await cls._line_schedules(session, line.id)
        cancelled_future = ZERO
        cancelled_count = 0
        for later in siblings:
            if later.period_number <= schedule.period_number:
                continue
            if later.status in (
                BillingScheduleStatus.INVOICED,
                BillingScheduleStatus.COMPLETED,
            ):
                # Already billed: credit it rather than pretend it never was.
                cancelled_future += money(later.amount)
            later.status = BillingScheduleStatus.CANCELLED
            later.detail = {
                **(later.detail or {}),
                "cancelled_at": datetime.now(UTC).isoformat(),
                "cancellation_effective_date": effective.isoformat(),
            }
            cancelled_count += 1

        was_invoiced = schedule.status in (
            BillingScheduleStatus.INVOICED,
            BillingScheduleStatus.COMPLETED,
        )
        # Only money already charged can be credited. An uninvoiced period is
        # simply reduced to what was consumed.
        refundable = money(
            (unused.prorated_amount if was_invoiced else ZERO) + cancelled_future
        )

        schedule.amount = consumed
        schedule.total_amount = money(consumed + Decimal(schedule.tax_amount))
        schedule.is_prorated = True
        schedule.proration_factor = unused.proration_factor
        schedule.status = BillingScheduleStatus.CANCELLED
        schedule.detail = {
            **(schedule.detail or {}),
            "cancelled_at": datetime.now(UTC).isoformat(),
            "cancellation_effective_date": effective.isoformat(),
            "period_amount": str(period_amount),
            "consumed_amount": str(consumed),
            "unused_amount": str(unused.prorated_amount),
            "was_invoiced": was_invoiced,
            "proration_explanation": unused.explanation,
        }

        credit_note_id: uuid.UUID | None = None
        if refundable > ZERO:
            note = await cls._issue_credit_note(
                session,
                order=order,
                schedule=schedule,
                actor=actor,
                amount=refundable,
                reason=CreditNoteReason.SUBSCRIPTION_CANCELLED,
                reason_note=reason
                or (
                    f"Cancellation of '{line.description}' effective "
                    f"{effective.isoformat()}."
                ),
                detail={
                    "period_amount": str(period_amount),
                    "consumed_amount": str(consumed),
                    "unused_current_period": str(unused.prorated_amount),
                    "cancelled_future_billed": str(cancelled_future),
                    "proration": unused.explanation,
                },
            )
            credit_note_id = note.id

        await session.flush()

        explanation = (
            f"'{line.description}' cancelled effective {effective.isoformat()}. "
            f"{consumed} of the {period_amount} period was consumed; "
            f"{unused.prorated_amount} was unused and "
            f"{cancelled_count} later period(s) were cancelled. "
            + (
                f"A credit note for {refundable} was issued."
                if refundable > ZERO
                else "Nothing had been invoiced, so no credit note was needed."
            )
        )

        await AuditService.emit(
            session,
            EventType.SUBSCRIPTION_CANCELLED,
            organization_id=order.organization_id,
            entity_type="billing_schedule",
            entity_id=schedule.id,
            actor=actor,
            payload={
                "order_number": order.order_number,
                "schedule_number": schedule.schedule_number,
                "effective_date": effective.isoformat(),
                "period_amount": str(period_amount),
                "consumed_amount": str(consumed),
                "unused_amount": str(unused.prorated_amount),
                "future_periods_cancelled": cancelled_count,
                "credit_note_amount": str(refundable),
                "reason": reason,
            },
        )

        return SubscriptionChangeResult(
            change_type=SubscriptionChangeType.CANCELLATION,
            sales_order_line_id=line.id,
            effective_date=effective,
            periods_kept=schedule.period_number,
            periods_regenerated=cancelled_count,
            previous_period_amount=period_amount,
            new_period_amount=consumed,
            proration_credit=refundable,
            proration_charge=ZERO,
            credit_note_id=credit_note_id,
            schedules=[
                {
                    "schedule_number": s.schedule_number,
                    "period_number": s.period_number,
                    "status": s.status.value,
                    "amount": str(money(s.amount)),
                    "period_start": s.period_start.isoformat(),
                    "period_end": s.period_end.isoformat(),
                }
                for s in await cls._line_schedules(session, line.id)
            ],
            explanation=explanation,
        )

    # ------------------------------------------------------- credit notes
    @staticmethod
    async def _next_credit_note_number(
        session: AsyncSession, organization_id: uuid.UUID
    ) -> str:
        count = (
            await session.execute(
                select(func.count())
                .select_from(CreditNote)
                .where(CreditNote.organization_id == organization_id)
            )
        ).scalar_one()
        return f"CN-{int(count) + 1:05d}"

    @classmethod
    async def _issue_credit_note(
        cls,
        session: AsyncSession,
        *,
        order: SalesOrder,
        schedule: BillingSchedule | None,
        actor: User,
        amount: Decimal,
        reason: CreditNoteReason,
        reason_note: str,
        detail: dict[str, Any] | None = None,
    ) -> CreditNote:
        invoice_id: uuid.UUID | None = None
        if schedule is not None:
            invoice_id = (
                await session.execute(
                    select(Invoice.id)
                    .where(Invoice.billing_schedule_id == schedule.id)
                    .order_by(Invoice.issue_date.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        note = CreditNote(
            organization_id=order.organization_id,
            credit_note_number=await cls._next_credit_note_number(
                session, order.organization_id
            ),
            sales_order_id=order.id,
            invoice_id=invoice_id,
            billing_schedule_id=schedule.id if schedule is not None else None,
            customer_organization_id=order.customer_organization_id,
            status=CreditNoteStatus.ISSUED,
            reason=reason,
            reason_note=reason_note,
            currency=order.currency,
            subtotal=money(amount),
            tax_amount=ZERO,
            total_amount=money(amount),
            amount_refunded=ZERO,
            issue_date=datetime.now(UTC).date(),
            issued_by_user_id=actor.id,
            detail=detail or {},
        )
        session.add(note)
        await session.flush()

        await AuditService.emit(
            session,
            EventType.CREDIT_NOTE_ISSUED,
            organization_id=order.organization_id,
            entity_type="credit_note",
            entity_id=note.id,
            actor=actor,
            payload={
                "credit_note_number": note.credit_note_number,
                "order_number": order.order_number,
                "amount": str(money(amount)),
                "reason": reason.value,
                "reason_note": reason_note,
                "invoice_id": str(invoice_id) if invoice_id else None,
            },
        )
        return note

    @classmethod
    async def refund_credit_note(
        cls,
        session: AsyncSession,
        *,
        note: CreditNote,
        actor: User,
        amount: Decimal | None = None,
    ) -> CreditNote:
        """Record cash actually returned against a credit note.

        This is what makes `PaymentStatus.REFUNDED` reachable — PDF A5's
        "partial refund" requirement.
        """
        if note.status is CreditNoteStatus.VOID:
            raise ConflictError(
                "A voided credit note cannot be refunded.",
                code="CREDIT_NOTE_VOID",
                details={"credit_note_number": note.credit_note_number},
            )
        outstanding = note.amount_outstanding
        requested = money(amount) if amount is not None else outstanding
        if requested <= ZERO:
            raise BusinessRuleError(
                "Refund amount must be greater than zero.",
                code="INVALID_REFUND_AMOUNT",
            )
        if requested > outstanding:
            raise BusinessRuleError(
                f"Refund of {requested} exceeds the outstanding credit of "
                f"{outstanding}.",
                code="REFUND_EXCEEDS_CREDIT",
                details={"amount_outstanding": str(outstanding)},
            )

        note.amount_refunded = money(Decimal(note.amount_refunded) + requested)
        if note.amount_refunded >= Decimal(note.total_amount):
            note.status = CreditNoteStatus.APPLIED

        if note.invoice_id is not None:
            invoice = await session.get(Invoice, note.invoice_id)
            if invoice is not None:
                count = (
                    await session.execute(
                        select(func.count())
                        .select_from(Payment)
                        .where(Payment.organization_id == note.organization_id)
                    )
                ).scalar_one()
                session.add(
                    Payment(
                        organization_id=note.organization_id,
                        payment_number=f"PAY-{int(count) + 1:05d}",
                        invoice_id=invoice.id,
                        amount=requested,
                        currency=note.currency,
                        method=(
                            await session.execute(
                                select(Payment.method)
                                .where(Payment.invoice_id == invoice.id)
                                .limit(1)
                            )
                        ).scalar_one_or_none()
                        or None,
                        status=PaymentStatus.REFUNDED,
                        reference=note.credit_note_number,
                        notes=f"Refund against {note.credit_note_number}.",
                        recorded_by_user_id=actor.id,
                    )
                )
                # The invoice is no longer fully settled once money goes back.
                invoice.amount_paid = money(
                    max(ZERO, Decimal(invoice.amount_paid) - requested)
                )
                invoice.status = (
                    InvoiceStatus.PAID
                    if invoice.amount_paid >= Decimal(invoice.total_amount)
                    else InvoiceStatus.PARTIALLY_PAID
                    if invoice.amount_paid > ZERO
                    else InvoiceStatus.ISSUED
                )

        await session.flush()
        await AuditService.emit(
            session,
            EventType.CREDIT_NOTE_REFUNDED,
            organization_id=note.organization_id,
            entity_type="credit_note",
            entity_id=note.id,
            actor=actor,
            payload={
                "credit_note_number": note.credit_note_number,
                "amount": str(requested),
                "amount_refunded_total": str(money(note.amount_refunded)),
                "status": note.status.value,
            },
        )
        return note

    @classmethod
    async def void_credit_note(
        cls, session: AsyncSession, *, note: CreditNote, actor: User, reason: str
    ) -> CreditNote:
        if note.status is CreditNoteStatus.VOID:
            raise ConflictError(
                "This credit note is already void.",
                code="CREDIT_NOTE_VOID",
                details={"credit_note_number": note.credit_note_number},
            )
        if Decimal(note.amount_refunded) > ZERO:
            raise ConflictError(
                "A credit note that has been partly refunded cannot be voided.",
                code="CREDIT_NOTE_PARTLY_REFUNDED",
                details={"amount_refunded": str(money(note.amount_refunded))},
            )
        note.status = CreditNoteStatus.VOID
        note.voided_at = datetime.now(UTC)
        note.reason_note = f"{note.reason_note or ''}\nVoided: {reason}".strip()
        await session.flush()
        await AuditService.emit(
            session,
            EventType.CREDIT_NOTE_VOIDED,
            organization_id=note.organization_id,
            entity_type="credit_note",
            entity_id=note.id,
            actor=actor,
            payload={
                "credit_note_number": note.credit_note_number,
                "reason": reason,
            },
        )
        return note
