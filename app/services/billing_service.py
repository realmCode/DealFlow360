"""BillingService — one-time and recurring schedules derived from order lines.

Billing is never invented: every schedule row traces back to a
``sales_order_lines`` row, and the sum of a line's schedules equals that line's
net amount **exactly**. The final period absorbs any rounding remainder, so
``SUM(amount) == line.net_amount`` holds for any period count.

A single order routinely carries both kinds at once — laptops, monitors and
installation bill once; the annual support plan bills on a recurring schedule.
"""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    INTERVAL_MONTHS,
    BillingScheduleStatus,
    BillingType,
    PaymentTerms,
    RecurringInterval,
)
from app.errors import BusinessRuleError
from app.events import EventType
from app.models.billing_schedule import BillingSchedule
from app.models.sales_order import SalesOrder
from app.models.sales_order_line import SalesOrderLine
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.commercial_engine import ZERO, money

TERMS_DAYS: dict[PaymentTerms, int] = {
    PaymentTerms.PREPAID: 0,
    PaymentTerms.NET_15: 15,
    PaymentTerms.NET_30: 30,
    PaymentTerms.NET_45: 45,
    PaymentTerms.NET_60: 60,
    PaymentTerms.NET_90: 90,
}


def add_months(anchor: date, months: int) -> date:
    """Add months, clamping to the end of the target month (31 Jan +1 -> 28 Feb)."""
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@dataclass(slots=True)
class ProrationResult:
    full_period_amount: Decimal
    days_in_period: int
    days_billed: int
    proration_factor: Decimal
    prorated_amount: Decimal
    explanation: str


class BillingService:
    # ---------------------------------------------------------- proration
    @staticmethod
    def prorate(
        *,
        full_period_amount: Decimal,
        period_start: date,
        period_end: date,
        billed_from: date,
    ) -> ProrationResult:
        """Day-count proration of a partial first period.

        Both endpoints are inclusive, so a 1-31 January period is 31 days and
        billing from the 16th covers 16 of them.
        """
        if period_end < period_start:
            raise BusinessRuleError(
                "period_end cannot precede period_start.", code="INVALID_PERIOD"
            )
        if billed_from < period_start or billed_from > period_end:
            raise BusinessRuleError(
                "billed_from must fall inside the period.", code="INVALID_PRORATION"
            )

        days_in_period = (period_end - period_start).days + 1
        days_billed = (period_end - billed_from).days + 1
        factor = (
            Decimal(days_billed) / Decimal(days_in_period)
        ).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        amount = money(Decimal(full_period_amount) * factor)

        return ProrationResult(
            full_period_amount=money(full_period_amount),
            days_in_period=days_in_period,
            days_billed=days_billed,
            proration_factor=factor,
            prorated_amount=amount,
            explanation=(
                f"Billing starts {billed_from.isoformat()} inside the period "
                f"{period_start.isoformat()} to {period_end.isoformat()} "
                f"({days_billed} of {days_in_period} days), so "
                f"{money(full_period_amount)} is prorated to {amount}."
            ),
        )

    @staticmethod
    def split_amount(total: Decimal, periods: int) -> list[Decimal]:
        """Split a total into ``periods`` amounts that sum back exactly."""
        if periods < 1:
            raise BusinessRuleError(
                "A recurring line must have at least one period.",
                code="INVALID_PERIOD_COUNT",
            )
        total = money(total)
        per = money(total / Decimal(periods))
        amounts = [per] * (periods - 1)
        amounts.append(money(total - per * Decimal(periods - 1)))
        return amounts

    # ------------------------------------------------------ build schedules
    @classmethod
    async def create_schedules_for_order(
        cls,
        session: AsyncSession,
        *,
        order: SalesOrder,
        actor: User | None,
        lines: Sequence[SalesOrderLine] | None = None,
        align_first_period_to_month_start: bool = False,
    ) -> list[BillingSchedule]:
        """Derive every billing obligation for an order.

        ``align_first_period_to_month_start`` bills the remainder of the
        calendar period first (prorated) and then moves to clean boundaries —
        the behaviour finance teams usually want for subscriptions.
        """
        if lines is None:
            lines = list(
                (
                    await session.execute(
                        select(SalesOrderLine)
                        .where(SalesOrderLine.sales_order_id == order.id)
                        .order_by(SalesOrderLine.line_number)
                    )
                ).scalars()
            )

        existing = (
            await session.execute(
                select(func.count())
                .select_from(BillingSchedule)
                .where(BillingSchedule.sales_order_id == order.id)
            )
        ).scalar_one()
        if int(existing) > 0:
            return list(
                (
                    await session.execute(
                        select(BillingSchedule)
                        .where(BillingSchedule.sales_order_id == order.id)
                        .order_by(
                            BillingSchedule.billing_type,
                            BillingSchedule.period_number,
                        )
                    )
                ).scalars()
            )

        terms_days = TERMS_DAYS[order.payment_terms]
        start = order.confirmed_at.date()
        created: list[BillingSchedule] = []
        counter = 0

        for line in lines:
            if line.billing_type is BillingType.ONE_TIME:
                counter += 1
                created.append(
                    BillingSchedule(
                        organization_id=order.organization_id,
                        schedule_number=f"{order.order_number}-B{counter:03d}",
                        sales_order_id=order.id,
                        sales_order_line_id=line.id,
                        billing_type=BillingType.ONE_TIME,
                        recurring_interval=None,
                        status=BillingScheduleStatus.SCHEDULED,
                        currency=order.currency,
                        amount=money(line.net_amount),
                        tax_amount=money(line.tax_amount),
                        total_amount=money(line.total_amount),
                        period_number=1,
                        total_periods=1,
                        period_start=start,
                        period_end=start,
                        due_date=start + timedelta(days=terms_days),
                        description=f"{line.description} (one-time)",
                        detail={
                            "quantity": str(line.quantity),
                            "unit_net_price": str(line.unit_net_price),
                            "category": line.category.value,
                        },
                    )
                )
                continue

            interval = line.recurring_interval or RecurringInterval.MONTHLY
            months = INTERVAL_MONTHS[interval]
            periods = max(1, int(line.recurring_periods))
            amounts = cls.split_amount(Decimal(line.net_amount), periods)
            tax_amounts = cls.split_amount(Decimal(line.tax_amount), periods)

            period_start = start
            for index in range(periods):
                counter += 1
                period_end = add_months(period_start, months) - timedelta(days=1)
                amount = amounts[index]
                tax_amount = tax_amounts[index]
                factor = Decimal("1.00000000")
                prorated = False

                if index == 0 and align_first_period_to_month_start:
                    boundary_start = date(period_start.year, period_start.month, 1)
                    boundary_end = add_months(boundary_start, months) - timedelta(days=1)
                    result = cls.prorate(
                        full_period_amount=amount,
                        period_start=boundary_start,
                        period_end=boundary_end,
                        billed_from=period_start,
                    )
                    amount = result.prorated_amount
                    tax_amount = money(tax_amount * result.proration_factor)
                    factor = result.proration_factor
                    prorated = True
                    period_end = boundary_end

                created.append(
                    BillingSchedule(
                        organization_id=order.organization_id,
                        schedule_number=f"{order.order_number}-B{counter:03d}",
                        sales_order_id=order.id,
                        sales_order_line_id=line.id,
                        billing_type=BillingType.RECURRING,
                        recurring_interval=interval,
                        status=BillingScheduleStatus.SCHEDULED,
                        currency=order.currency,
                        amount=amount,
                        tax_amount=tax_amount,
                        total_amount=money(amount + tax_amount),
                        period_number=index + 1,
                        total_periods=periods,
                        period_start=period_start,
                        period_end=period_end,
                        due_date=period_start + timedelta(days=terms_days),
                        is_prorated=prorated,
                        proration_factor=factor,
                        description=(
                            f"{line.description} ({interval.value.lower()}, period "
                            f"{index + 1} of {periods})"
                        ),
                        detail={
                            "quantity": str(line.quantity),
                            "unit_net_price": str(line.unit_net_price),
                            "category": line.category.value,
                            "interval_months": months,
                        },
                    )
                )
                period_start = period_end + timedelta(days=1)

        for schedule in created:
            session.add(schedule)
        await session.flush()

        one_time = money(
            sum(
                (s.amount for s in created if s.billing_type is BillingType.ONE_TIME),
                ZERO,
            )
        )
        recurring = money(
            sum(
                (s.amount for s in created if s.billing_type is BillingType.RECURRING),
                ZERO,
            )
        )
        await AuditService.emit(
            session,
            EventType.BILLING_SCHEDULED,
            organization_id=order.organization_id,
            entity_type="sales_order",
            entity_id=order.id,
            actor=actor,
            payload={
                "order_number": order.order_number,
                "schedule_count": len(created),
                "one_time_total": str(one_time),
                "recurring_total": str(recurring),
                "schedules": [
                    {
                        "schedule_number": s.schedule_number,
                        "billing_type": s.billing_type.value,
                        "recurring_interval": (
                            s.recurring_interval.value if s.recurring_interval else None
                        ),
                        "amount": str(s.amount),
                        "period": f"{s.period_number}/{s.total_periods}",
                        "due_date": s.due_date.isoformat(),
                    }
                    for s in created
                ],
            },
        )
        return created

    # ------------------------------------------------------------ read side
    @staticmethod
    async def list_schedules(
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        sales_order_id: uuid.UUID | None = None,
        billing_type: BillingType | None = None,
    ) -> list[BillingSchedule]:
        stmt = select(BillingSchedule).where(
            BillingSchedule.organization_id == organization_id
        )
        if sales_order_id is not None:
            stmt = stmt.where(BillingSchedule.sales_order_id == sales_order_id)
        if billing_type is not None:
            stmt = stmt.where(BillingSchedule.billing_type == billing_type)
        stmt = stmt.order_by(
            BillingSchedule.sales_order_id,
            BillingSchedule.billing_type,
            BillingSchedule.period_number,
        )
        return list((await session.execute(stmt)).scalars())

    @staticmethod
    async def summarise(
        session: AsyncSession, order: SalesOrder
    ) -> dict[str, Any]:
        schedules = list(
            (
                await session.execute(
                    select(BillingSchedule).where(
                        BillingSchedule.sales_order_id == order.id
                    )
                )
            ).scalars()
        )
        one_time = money(
            sum(
                (s.amount for s in schedules if s.billing_type is BillingType.ONE_TIME),
                ZERO,
            )
        )
        recurring_total = money(
            sum(
                (
                    s.amount
                    for s in schedules
                    if s.billing_type is BillingType.RECURRING
                ),
                ZERO,
            )
        )
        annualised = ZERO
        for schedule in schedules:
            if schedule.billing_type is not BillingType.RECURRING:
                continue
            months = INTERVAL_MONTHS[
                schedule.recurring_interval or RecurringInterval.MONTHLY
            ]
            annualised += Decimal(schedule.amount) * (Decimal("12") / Decimal(months))
            break  # one period is enough to annualise a level schedule

        return {
            "sales_order_id": order.id,
            "one_time_total": one_time,
            "recurring_total_per_year": money(annualised),
            "recurring_contract_total": recurring_total,
            "grand_total": money(one_time + recurring_total),
            "schedule_count": len(schedules),
            "one_time_count": Decimal(
                len([s for s in schedules if s.billing_type is BillingType.ONE_TIME])
            ),
            "recurring_count": Decimal(
                len([s for s in schedules if s.billing_type is BillingType.RECURRING])
            ),
        }
