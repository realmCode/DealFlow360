"""CommercialEngine — the only place money is calculated.

Every figure the API returns for a quote is produced here and persisted. The
frontend is a renderer: it never computes a total, a discount, a tax amount or
a margin.

Arithmetic rules
----------------
* ``Decimal`` throughout; ``float`` appears nowhere.
* Money quantised to 2dp, unit prices to 4dp, percentages to 4dp.
* Rounding is ``ROUND_HALF_UP`` — the convention finance teams expect.
* Rounding happens **per line**, then lines are summed. Summing unrounded
  values and rounding once would make the printed line items fail to add up to
  the printed total, which is worse than a sub-cent aggregate difference.
* ``margin`` is measured against **net revenue excluding tax**: tax is
  collected on behalf of a tax authority and is not the seller's revenue.

Line amount definition
----------------------
``gross_amount = quantity × unit_list_price × recurring_periods``

For one-time lines ``recurring_periods`` is 1, so this reduces to the obvious
formula. For recurring lines ``unit_list_price`` is the price *per period*, so
multiplying by the period count yields total contract value — which is what
discount ceilings and margin floors must be judged against.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import BillingType, CustomerTier
from app.models.commercial_snapshot import CommercialSnapshot
from app.models.customer_profile import CustomerProfile
from app.models.quote_line import QuoteLine
from app.models.quote_version import QuoteVersion

ZERO = Decimal("0")
HUNDRED = Decimal("100")
MONEY_Q = Decimal("0.01")
UNIT_Q = Decimal("0.0001")
PCT_Q = Decimal("0.0001")


def money(value: Decimal) -> Decimal:
    """Quantise to 2dp, ROUND_HALF_UP."""
    return Decimal(value).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def unit(value: Decimal) -> Decimal:
    """Quantise a per-unit price to 4dp."""
    return Decimal(value).quantize(UNIT_Q, rounding=ROUND_HALF_UP)


def pct(value: Decimal) -> Decimal:
    """Quantise a percentage to 4dp."""
    return Decimal(value).quantize(PCT_Q, rounding=ROUND_HALF_UP)


def format_quantity(value: Decimal) -> str:
    """Render a quantity for human prose: 60.0000 -> '60', 1.5000 -> '1.5'.

    Used in explanations and attention items. Storage keeps 4dp; operators
    should not have to read them.
    """
    normalized = Decimal(value).normalize()
    if normalized == normalized.to_integral_value():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def safe_pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    """``numerator / denominator × 100``, or 0 when the denominator is 0."""
    if denominator == ZERO:
        return pct(ZERO)
    return pct(numerator / denominator * HUNDRED)


@dataclass(slots=True)
class LineCalculation:
    """Derived values for one line. Pure output — no DB access."""

    unit_net_price: Decimal
    gross_amount: Decimal
    discount_amount: Decimal
    net_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    line_cost: Decimal
    line_margin: Decimal
    line_margin_pct: Decimal


@dataclass(slots=True)
class QuoteTotals:
    """Derived totals for a whole version. Pure output — no DB access."""

    gross_revenue: Decimal = ZERO
    total_discount: Decimal = ZERO
    net_revenue: Decimal = ZERO
    tax_amount: Decimal = ZERO
    total_revenue: Decimal = ZERO
    total_cost: Decimal = ZERO
    margin: Decimal = ZERO
    margin_pct: Decimal = ZERO
    effective_discount_pct: Decimal = ZERO
    one_time_revenue: Decimal = ZERO
    recurring_revenue: Decimal = ZERO
    line_count: int = 0
    lines: list[dict[str, Any]] = field(default_factory=list)


class CommercialEngine:
    """Stateless calculator + persistence of authoritative financials."""

    # ------------------------------------------------------------ pure maths
    @staticmethod
    def calculate_line(
        *,
        quantity: Decimal,
        unit_list_price: Decimal,
        unit_cost: Decimal,
        discount_pct: Decimal = ZERO,
        tax_rate_pct: Decimal = ZERO,
        recurring_periods: int = 1,
    ) -> LineCalculation:
        quantity = Decimal(quantity)
        unit_list_price = Decimal(unit_list_price)
        unit_cost = Decimal(unit_cost)
        discount_pct = Decimal(discount_pct)
        tax_rate_pct = Decimal(tax_rate_pct)
        periods = Decimal(recurring_periods)

        gross_amount = money(quantity * unit_list_price * periods)
        discount_amount = money(gross_amount * discount_pct / HUNDRED)
        net_amount = money(gross_amount - discount_amount)
        unit_net_price = unit(unit_list_price * (HUNDRED - discount_pct) / HUNDRED)
        tax_amount = money(net_amount * tax_rate_pct / HUNDRED)
        total_amount = money(net_amount + tax_amount)
        line_cost = money(quantity * unit_cost * periods)
        line_margin = money(net_amount - line_cost)

        return LineCalculation(
            unit_net_price=unit_net_price,
            gross_amount=gross_amount,
            discount_amount=discount_amount,
            net_amount=net_amount,
            tax_amount=tax_amount,
            total_amount=total_amount,
            line_cost=line_cost,
            line_margin=line_margin,
            line_margin_pct=safe_pct(line_margin, net_amount),
        )

    @staticmethod
    def total_from_calculations(
        items: Sequence[tuple[LineCalculation, BillingType]],
    ) -> QuoteTotals:
        totals = QuoteTotals(line_count=len(items))
        for calc, billing_type in items:
            totals.gross_revenue += calc.gross_amount
            totals.total_discount += calc.discount_amount
            totals.net_revenue += calc.net_amount
            totals.tax_amount += calc.tax_amount
            totals.total_cost += calc.line_cost
            if billing_type is BillingType.RECURRING:
                totals.recurring_revenue += calc.net_amount
            else:
                totals.one_time_revenue += calc.net_amount

        totals.gross_revenue = money(totals.gross_revenue)
        totals.total_discount = money(totals.total_discount)
        totals.net_revenue = money(totals.net_revenue)
        totals.tax_amount = money(totals.tax_amount)
        totals.total_cost = money(totals.total_cost)
        totals.one_time_revenue = money(totals.one_time_revenue)
        totals.recurring_revenue = money(totals.recurring_revenue)

        totals.total_revenue = money(totals.net_revenue + totals.tax_amount)
        totals.margin = money(totals.net_revenue - totals.total_cost)
        totals.margin_pct = safe_pct(totals.margin, totals.net_revenue)
        totals.effective_discount_pct = safe_pct(
            totals.total_discount, totals.gross_revenue
        )
        return totals

    # ------------------------------------------------------ persistence path
    @classmethod
    def apply_to_line(cls, line: QuoteLine) -> LineCalculation:
        """Recalculate one ORM line in place and return the derived values."""
        calc = cls.calculate_line(
            quantity=line.quantity,
            unit_list_price=line.unit_list_price,
            unit_cost=line.unit_cost,
            discount_pct=line.discount_pct,
            tax_rate_pct=line.tax_rate_pct,
            recurring_periods=line.recurring_periods,
        )
        line.unit_net_price = calc.unit_net_price
        line.gross_amount = calc.gross_amount
        line.discount_amount = calc.discount_amount
        line.net_amount = calc.net_amount
        line.tax_amount = calc.tax_amount
        line.total_amount = calc.total_amount
        line.line_cost = calc.line_cost
        line.line_margin = calc.line_margin
        line.line_margin_pct = calc.line_margin_pct
        return calc

    @classmethod
    async def load_lines(
        cls, session: AsyncSession, version_id: uuid.UUID
    ) -> list[QuoteLine]:
        result = await session.execute(
            select(QuoteLine)
            .where(QuoteLine.quote_version_id == version_id)
            .order_by(QuoteLine.line_number)
        )
        return list(result.scalars())

    @classmethod
    async def calculate_version(
        cls,
        session: AsyncSession,
        version: QuoteVersion,
        *,
        lines: Iterable[QuoteLine] | None = None,
        persist_snapshot: bool = True,
    ) -> QuoteTotals:
        """Recalculate every line, write the version totals, snapshot the result.

        This is the *only* code path that writes ``quote_versions`` financial
        columns, which is what makes the stored numbers trustworthy.
        """
        line_list = (
            list(lines) if lines is not None else await cls.load_lines(session, version.id)
        )

        calcs: list[tuple[LineCalculation, BillingType]] = []
        line_details: list[dict[str, Any]] = []
        for line in line_list:
            calc = cls.apply_to_line(line)
            calcs.append((calc, line.billing_type))
            line_details.append(
                {
                    "quote_line_id": str(line.id),
                    "product_id": str(line.product_id),
                    "line_number": line.line_number,
                    "description": line.description,
                    "category": line.category.value,
                    "quantity": str(line.quantity),
                    "unit_list_price": str(line.unit_list_price),
                    "unit_cost": str(line.unit_cost),
                    "unit_net_price": str(calc.unit_net_price),
                    "discount_pct": str(line.discount_pct),
                    "gross_amount": str(calc.gross_amount),
                    "discount_amount": str(calc.discount_amount),
                    "net_amount": str(calc.net_amount),
                    "tax_amount": str(calc.tax_amount),
                    "total_amount": str(calc.total_amount),
                    "line_cost": str(calc.line_cost),
                    "line_margin": str(calc.line_margin),
                    "line_margin_pct": str(calc.line_margin_pct),
                    "billing_type": line.billing_type.value,
                    "recurring_interval": (
                        line.recurring_interval.value if line.recurring_interval else None
                    ),
                    "recurring_periods": line.recurring_periods,
                }
            )

        totals = cls.total_from_calculations(calcs)
        totals.lines = line_details

        version.gross_revenue = totals.gross_revenue
        version.total_discount = totals.total_discount
        version.net_revenue = totals.net_revenue
        version.tax_amount = totals.tax_amount
        version.total_revenue = totals.total_revenue
        version.total_cost = totals.total_cost
        version.margin = totals.margin
        version.margin_pct = totals.margin_pct
        version.effective_discount_pct = totals.effective_discount_pct
        version.one_time_revenue = totals.one_time_revenue
        version.recurring_revenue = totals.recurring_revenue
        version.calculated_at = datetime.now(UTC)

        await session.flush()

        if persist_snapshot:
            await cls._write_snapshot(session, version, totals)

        return totals

    @classmethod
    async def _write_snapshot(
        cls, session: AsyncSession, version: QuoteVersion, totals: QuoteTotals
    ) -> CommercialSnapshot:
        profile = await cls._customer_profile_for_version(session, version)

        await session.execute(
            update(CommercialSnapshot)
            .where(
                CommercialSnapshot.quote_version_id == version.id,
                CommercialSnapshot.is_current.is_(True),
            )
            .values(is_current=False)
        )

        snapshot = CommercialSnapshot(
            organization_id=version.organization_id,
            quote_version_id=version.id,
            gross_revenue=totals.gross_revenue,
            total_discount=totals.total_discount,
            revenue=totals.net_revenue,
            tax_amount=totals.tax_amount,
            cost=totals.total_cost,
            margin=totals.margin,
            margin_pct=totals.margin_pct,
            effective_discount_pct=totals.effective_discount_pct,
            one_time_revenue=totals.one_time_revenue,
            recurring_revenue=totals.recurring_revenue,
            blended_risk_score=version.blended_risk_score,
            payment_terms=version.payment_terms,
            customer_tier=profile.tier if profile else CustomerTier.BRONZE,
            snapshot_json={
                "version_number": version.version_number,
                "status": version.status.value,
                "currency": version.currency,
                "line_count": totals.line_count,
                "lines": totals.lines,
                "totals": {
                    "gross_revenue": str(totals.gross_revenue),
                    "total_discount": str(totals.total_discount),
                    "net_revenue": str(totals.net_revenue),
                    "tax_amount": str(totals.tax_amount),
                    "total_revenue": str(totals.total_revenue),
                    "total_cost": str(totals.total_cost),
                    "margin": str(totals.margin),
                    "margin_pct": str(totals.margin_pct),
                    "effective_discount_pct": str(totals.effective_discount_pct),
                    "one_time_revenue": str(totals.one_time_revenue),
                    "recurring_revenue": str(totals.recurring_revenue),
                },
            },
            is_current=True,
            calculated_at=datetime.now(UTC),
        )
        session.add(snapshot)
        await session.flush()
        return snapshot

    @staticmethod
    async def _customer_profile_for_version(
        session: AsyncSession, version: QuoteVersion
    ) -> CustomerProfile | None:
        from app.models.deal import Deal
        from app.models.quote import Quote

        result = await session.execute(
            select(CustomerProfile)
            .join(Deal, Deal.customer_profile_id == CustomerProfile.id)
            .join(Quote, Quote.deal_id == Deal.id)
            .where(Quote.id == version.quote_id)
        )
        return result.scalars().first()

    @staticmethod
    async def current_snapshot(
        session: AsyncSession, version_id: uuid.UUID
    ) -> CommercialSnapshot | None:
        result = await session.execute(
            select(CommercialSnapshot)
            .where(
                CommercialSnapshot.quote_version_id == version_id,
                CommercialSnapshot.is_current.is_(True),
            )
            .order_by(CommercialSnapshot.calculated_at.desc())
        )
        return result.scalars().first()
