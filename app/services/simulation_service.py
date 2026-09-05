"""What-if simulation — score a hypothetical quote without persisting it.

The problem this solves: a rep can currently only discover the approval
consequence of a discount by submitting it. That drags an approver into every
experiment and makes the governance engine feel like an obstacle rather than a
guide.

The implementation is deliberately thin. `CommercialEngine.calculate_line` and
`PolicyEngine.evaluate` are already pure functions of their arguments — no I/O,
no session — so this module loads the real lines, clones them **in memory**,
applies the hypothetical changes and calls the same two functions the real path
calls. The score a simulation reports is therefore the score a submit would
produce, by construction rather than by a parallel implementation that could
drift.

Nothing is written: no version, no snapshot, no policy result, no audit event.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import BillingType, PaymentTerms, ProductCategory, RecurringInterval
from app.errors import NotFoundError
from app.models.quote_line import QuoteLine
from app.models.quote_version import QuoteVersion
from app.services.commercial_engine import ZERO, CommercialEngine, money, pct
from app.services.policy_engine import PolicyEngine
from app.services.quote_service import QuoteService
from app.services.settings_service import SettingsService


# Plain detached stand-ins rather than ORM copies. `copy.copy` of a mapped
# instance carries its InstrumentedAttribute machinery, so writing to the clone
# risks marking the real row dirty and flushing a hypothesis to the database —
# which is precisely what this feature must never do. These carry exactly the
# fields CommercialEngine and PolicyEngine read.
@dataclass(slots=True)
class _LineProbe:
    id: uuid.UUID
    description: str
    line_number: int
    category: ProductCategory
    quantity: Decimal
    unit_list_price: Decimal
    unit_cost: Decimal
    discount_pct: Decimal
    tax_rate_pct: Decimal
    recurring_periods: int
    billing_type: BillingType
    recurring_interval: RecurringInterval | None
    # Written back after calculation so PolicyEngine's revenue-share weighting
    # sees the hypothetical amounts rather than the stored ones.
    net_amount: Decimal = ZERO
    discount_amount: Decimal = ZERO
    effective_discount_pct: Decimal = ZERO

    @classmethod
    def of(cls, line: QuoteLine) -> "_LineProbe":
        return cls(
            id=line.id,
            description=line.description,
            line_number=line.line_number,
            category=line.category,
            quantity=Decimal(line.quantity),
            unit_list_price=Decimal(line.unit_list_price),
            unit_cost=Decimal(line.unit_cost),
            discount_pct=Decimal(line.discount_pct),
            tax_rate_pct=Decimal(line.tax_rate_pct),
            recurring_periods=int(line.recurring_periods),
            billing_type=line.billing_type,
            recurring_interval=line.recurring_interval,
            net_amount=Decimal(line.net_amount),
            discount_amount=Decimal(line.discount_amount),
            effective_discount_pct=Decimal(line.effective_discount_pct or ZERO),
        )


@dataclass(slots=True)
class _VersionProbe:
    """Every ``version.*`` attribute PolicyEngine.evaluate reads.

    Kept exhaustive on purpose: a missing field surfaces as an AttributeError
    the first time a policy type that needs it fires, which could be long
    after this code was written.
    """

    id: uuid.UUID
    organization_id: uuid.UUID
    quote_id: uuid.UUID
    currency: str
    payment_terms: PaymentTerms
    valid_until: date | None
    order_discount_pct: Decimal
    gross_revenue: Decimal
    total_discount: Decimal
    net_revenue: Decimal
    total_cost: Decimal
    margin: Decimal
    margin_pct: Decimal
    effective_discount_pct: Decimal
    blended_risk_score: Decimal
    risk_band: Any
    requires_approval: bool

    @classmethod
    def of(cls, version: QuoteVersion) -> "_VersionProbe":
        return cls(
            id=version.id,
            organization_id=version.organization_id,
            quote_id=version.quote_id,
            currency=version.currency,
            payment_terms=version.payment_terms,
            valid_until=version.valid_until,
            order_discount_pct=Decimal(version.order_discount_pct or ZERO),
            gross_revenue=Decimal(version.gross_revenue or ZERO),
            total_discount=Decimal(version.total_discount or ZERO),
            net_revenue=Decimal(version.net_revenue or ZERO),
            total_cost=Decimal(version.total_cost or ZERO),
            margin=Decimal(version.margin or ZERO),
            margin_pct=Decimal(version.margin_pct or ZERO),
            effective_discount_pct=Decimal(version.effective_discount_pct or ZERO),
            blended_risk_score=Decimal(version.blended_risk_score or ZERO),
            risk_band=version.risk_band,
            requires_approval=bool(version.requires_approval),
        )


class SimulationService:
    @staticmethod
    async def simulate(
        session: AsyncSession,
        *,
        version: QuoteVersion,
        line_discounts: dict[uuid.UUID, Decimal] | None = None,
        line_quantities: dict[uuid.UUID, Decimal] | None = None,
        order_discount_pct: Decimal | None = None,
        payment_terms: PaymentTerms | None = None,
    ) -> dict[str, Any]:
        line_discounts = line_discounts or {}
        line_quantities = line_quantities or {}

        real_lines = await CommercialEngine.load_lines(session, version.id)
        known = {line.id for line in real_lines}
        for line_id in set(line_discounts) | set(line_quantities):
            if line_id not in known:
                raise NotFoundError(
                    "That line is not on this quote version.",
                    details={"quote_line_id": str(line_id)},
                )

        quote = await QuoteService.get_quote(
            session, version.quote_id, version.organization_id
        )
        profile = await QuoteService.profile_for_quote(session, quote)
        policies = await PolicyEngine.active_policies(
            session, version.organization_id
        )
        org_settings = await SettingsService.for_org(
            session, version.organization_id
        )
        weights = {
            "overage": Decimal(org_settings.risk_discount_overage_weight),
            "breadth": Decimal(org_settings.risk_breadth_weight),
            "margin": Decimal(org_settings.risk_margin_weight),
            "depth": Decimal(org_settings.risk_depth_weight),
        }
        threshold = Decimal(org_settings.finance_escalation_threshold)

        # ------------------------------------------------------- baseline
        baseline = SimulationService._score(
            version=_VersionProbe.of(version),
            lines=[_LineProbe.of(line) for line in real_lines],
            profile=profile,
            policies=policies,
            weights=weights,
            threshold=threshold,
            order_discount_pct=Decimal(version.order_discount_pct or ZERO),
            payment_terms=version.payment_terms,
        )

        # ------------------------------------------------------ hypothesis
        hypothetical = []
        for line in real_lines:
            probe = _LineProbe.of(line)
            if line.id in line_discounts:
                probe.discount_pct = Decimal(line_discounts[line.id])
            if line.id in line_quantities:
                probe.quantity = Decimal(line_quantities[line.id])
            hypothetical.append(probe)

        proposed_order_discount = (
            Decimal(order_discount_pct)
            if order_discount_pct is not None
            else Decimal(version.order_discount_pct or ZERO)
        )
        proposed_terms = payment_terms or version.payment_terms

        proposed = SimulationService._score(
            version=_VersionProbe.of(version),
            lines=hypothetical,
            profile=profile,
            policies=policies,
            weights=weights,
            threshold=threshold,
            order_discount_pct=proposed_order_discount,
            payment_terms=proposed_terms,
        )

        added = [
            level
            for level in proposed["required_approvals"]
            if level not in baseline["required_approvals"]
        ]
        removed = [
            level
            for level in baseline["required_approvals"]
            if level not in proposed["required_approvals"]
        ]

        return {
            "quote_version_id": version.id,
            "simulated_at": datetime.now(UTC),
            "baseline": baseline,
            "proposed": proposed,
            "margin_delta": money(
                Decimal(proposed["margin"]) - Decimal(baseline["margin"])
            ),
            "margin_pct_delta": pct(
                Decimal(proposed["margin_pct"]) - Decimal(baseline["margin_pct"])
            ),
            "revenue_delta": money(
                Decimal(proposed["net_revenue"]) - Decimal(baseline["net_revenue"])
            ),
            "risk_delta": pct(
                Decimal(proposed["blended_risk_score"])
                - Decimal(baseline["blended_risk_score"])
            ),
            "approvals_added": added,
            "approvals_removed": removed,
            "verdict": SimulationService._verdict(baseline, proposed, added, removed),
            "persisted": False,
        }

    @staticmethod
    def _score(
        *,
        version: _VersionProbe,
        lines: list[_LineProbe],
        profile: Any,
        policies: Any,
        weights: dict[str, Decimal],
        threshold: Decimal,
        order_discount_pct: Decimal,
        payment_terms: PaymentTerms,
    ) -> dict[str, Any]:
        calcs = []
        line_previews: list[dict[str, Any]] = []
        for line in lines:
            calc = CommercialEngine.calculate_line(
                quantity=line.quantity,
                unit_list_price=line.unit_list_price,
                unit_cost=line.unit_cost,
                discount_pct=line.discount_pct,
                tax_rate_pct=line.tax_rate_pct,
                recurring_periods=line.recurring_periods,
                order_discount_pct=order_discount_pct,
            )
            # Write the results back onto the probe. PolicyEngine weights each
            # line's ceiling overage by its share of net revenue, so leaving
            # the stored amounts in place would divide new totals by old line
            # values and mis-score the hypothesis.
            line.net_amount = calc.net_amount
            line.discount_amount = calc.discount_amount
            line.effective_discount_pct = calc.effective_discount_pct

            calcs.append((calc, line.billing_type))
            line_previews.append(
                {
                    "quote_line_id": str(line.id),
                    "description": line.description,
                    "category": line.category.value,
                    "quantity": str(line.quantity),
                    "discount_pct": str(pct(line.discount_pct)),
                    "effective_discount_pct": str(calc.effective_discount_pct),
                    "net_amount": str(calc.net_amount),
                    "line_margin": str(calc.line_margin),
                    "line_margin_pct": str(calc.line_margin_pct),
                }
            )

        totals = CommercialEngine.total_from_calculations(calcs)

        version.order_discount_pct = order_discount_pct
        version.payment_terms = payment_terms
        version.net_revenue = totals.net_revenue
        version.gross_revenue = totals.gross_revenue
        version.total_discount = totals.total_discount
        version.total_cost = totals.total_cost
        version.margin = totals.margin
        version.margin_pct = totals.margin_pct
        version.effective_discount_pct = totals.effective_discount_pct

        evaluation = PolicyEngine.evaluate(
            version=version,
            lines=lines,
            profile=profile,
            policies=policies,
            weights=weights,
            escalation_threshold=threshold,
        )

        return {
            "gross_revenue": str(totals.gross_revenue),
            "total_discount": str(totals.total_discount),
            "order_discount_pct": str(pct(order_discount_pct)),
            "order_discount_amount": str(totals.order_discount_amount),
            "net_revenue": str(totals.net_revenue),
            "tax_amount": str(totals.tax_amount),
            "total_revenue": str(totals.total_revenue),
            "total_cost": str(totals.total_cost),
            "margin": str(totals.margin),
            "margin_pct": str(totals.margin_pct),
            "effective_discount_pct": str(totals.effective_discount_pct),
            "blended_risk_score": str(evaluation.blended_risk.score),
            "risk_band": evaluation.blended_risk.band.value,
            "risk_components": [
                c.as_dict() for c in evaluation.blended_risk.components
            ],
            "risk_explanation": evaluation.blended_risk.explanation,
            "requires_approval": evaluation.requires_approval,
            "required_approvals": [
                spec.level.value for spec in evaluation.required_approvals
            ],
            "violation_count": len(evaluation.violations),
            "violations": [v.reason for v in evaluation.violations],
            "payment_terms": payment_terms.value,
            "lines": line_previews,
        }

    @staticmethod
    def _verdict(
        baseline: dict[str, Any],
        proposed: dict[str, Any],
        added: list[str],
        removed: list[str],
    ) -> str:
        """One sentence a rep can act on without reading the numbers."""
        parts: list[str] = []

        margin_before = Decimal(baseline["margin_pct"])
        margin_after = Decimal(proposed["margin_pct"])
        if margin_after != margin_before:
            direction = "falls" if margin_after < margin_before else "rises"
            parts.append(
                f"Margin {direction} from {margin_before}% to {margin_after}%"
            )

        risk_before = Decimal(baseline["blended_risk_score"])
        risk_after = Decimal(proposed["blended_risk_score"])
        if risk_after != risk_before:
            parts.append(
                f"blended risk moves from {risk_before} "
                f"({baseline['risk_band']}) to {risk_after} "
                f"({proposed['risk_band']})"
            )

        if added:
            parts.append(f"this would newly require {', '.join(added)} approval")
        elif removed and not proposed["required_approvals"]:
            parts.append("this would no longer need any approval")
        elif removed:
            parts.append(f"{', '.join(removed)} approval would no longer be needed")
        elif proposed["requires_approval"]:
            parts.append(
                f"approval is still required from "
                f"{', '.join(proposed['required_approvals'])}"
            )
        else:
            parts.append("no approval would be required")

        if not parts:
            return "No change."
        return ". ".join(part[0].upper() + part[1:] for part in parts) + "."
