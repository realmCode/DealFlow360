"""RecommendationEngine — upsell / cross-sell suggestions (P1).

Deterministic and rule-based on purpose: a hackathon demo cannot defend a
black-box model, and every suggestion here can be justified out loud.

Rules, in priority order:

1. **Attach-rate cross-sell** — a hardware line with no matching service or
   subscription line is the classic missed attach.
2. **Margin repair** — when the quote breaches its margin floor, propose the
   highest-margin catalog item not already on the quote.
3. **Volume upsell** — hardware quantities just under a round threshold.

Each recommendation carries its own reasoning plus the margin impact, so the
seller can see what accepting it does to the deal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ProductCategory
from app.models.product import Product
from app.models.quote_line import QuoteLine
from app.models.quote_version import QuoteVersion
from app.services.commercial_engine import CommercialEngine, ZERO, money, pct, safe_pct

ATTACH_CATEGORIES = (ProductCategory.SERVICE, ProductCategory.SUBSCRIPTION)
VOLUME_THRESHOLDS = (Decimal("10"), Decimal("25"), Decimal("50"), Decimal("100"))


#: Ordering weight for the panel. Promoted products sort ahead of all of these.
_CONFIDENCE_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


@dataclass(slots=True)
class Recommendation:
    kind: str
    product_id: uuid.UUID | None
    product_name: str
    suggested_quantity: Decimal
    estimated_revenue: Decimal
    estimated_margin: Decimal
    estimated_margin_pct: Decimal
    reason: str
    impact: str
    confidence: str
    #: PDF B5 — drives the promotion tag in the upsell panel.
    is_promoted: bool = False
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "product_id": str(self.product_id) if self.product_id else None,
            "product_name": self.product_name,
            "suggested_quantity": str(self.suggested_quantity),
            "estimated_revenue": str(self.estimated_revenue),
            "estimated_margin": str(self.estimated_margin),
            "estimated_margin_pct": str(self.estimated_margin_pct),
            "reason": self.reason,
            "impact": self.impact,
            "confidence": self.confidence,
            "is_promoted": self.is_promoted,
            "detail": self.detail,
        }


class RecommendationEngine:
    @classmethod
    async def for_version(
        cls, session: AsyncSession, version: QuoteVersion
    ) -> list[dict[str, Any]]:
        from app.models.dismissed_recommendation import DismissedRecommendation
        from app.services.settings_service import SettingsService

        lines = await CommercialEngine.load_lines(session, version.id)
        catalog = list(
            (
                await session.execute(
                    select(Product).where(
                        Product.organization_id == version.organization_id,
                        Product.is_active.is_(True),
                    )
                )
            ).scalars()
        )

        # PDF A6.3 — "Set minimum margin thresholds so only healthy margin
        # suggestions surface". Suggesting a thin-margin product to fix a
        # margin problem would be actively counterproductive.
        org_settings = await SettingsService.for_org(
            session, version.organization_id
        )
        min_margin = Decimal(org_settings.recommendation_min_margin_pct)
        if min_margin > ZERO:
            catalog = [
                p
                for p in catalog
                if safe_pct(
                    Decimal(p.list_price) - Decimal(p.internal_cost),
                    Decimal(p.list_price),
                )
                >= min_margin
            ]

        # PDF B5 — a dismissed suggestion must stay dismissed, otherwise the
        # Dismiss button appears broken and the panel loses credibility.
        dismissed = set(
            (
                await session.execute(
                    select(DismissedRecommendation.product_id).where(
                        DismissedRecommendation.quote_version_id == version.id
                    )
                )
            ).scalars()
        )
        catalog = [p for p in catalog if p.id not in dismissed]

        on_quote = {line.product_id for line in lines}
        by_category: dict[ProductCategory, list[QuoteLine]] = {}
        for line in lines:
            by_category.setdefault(line.category, []).append(line)

        results: list[Recommendation] = []

        # ---------------------------------------------- 1. attach-rate gaps
        hardware = by_category.get(ProductCategory.HARDWARE, [])
        if hardware:
            hardware_units = sum((Decimal(line.quantity) for line in hardware), ZERO)
            for category in ATTACH_CATEGORIES:
                if by_category.get(category):
                    continue
                candidate = cls._best_margin_product(
                    [p for p in catalog if p.category is category and p.id not in on_quote]
                )
                if candidate is None:
                    continue
                quantity = (
                    hardware_units
                    if category is ProductCategory.SUBSCRIPTION
                    else Decimal("1")
                )
                results.append(
                    cls._build(
                        kind="CROSS_SELL",
                        product=candidate,
                        quantity=quantity,
                        reason=(
                            f"The quote contains {hardware_units} hardware units but "
                            f"no {category.value.lower()} line. "
                            f"'{candidate.name}' is the standard attach for this "
                            f"configuration."
                        ),
                        impact_prefix="Adding it would raise",
                        confidence="HIGH",
                    )
                )

        # ------------------------------------------------ 2. margin repair
        margin_floor_breached = Decimal(version.margin_pct or ZERO) < Decimal("10")
        if margin_floor_breached:
            candidate = cls._best_margin_product(
                [p for p in catalog if p.id not in on_quote]
            )
            if candidate is not None:
                results.append(
                    cls._build(
                        kind="MARGIN_REPAIR",
                        product=candidate,
                        quantity=Decimal("1"),
                        reason=(
                            f"Quote margin is "
                            f"{pct(version.margin_pct)}%. '{candidate.name}' carries "
                            f"a "
                            f"{safe_pct(Decimal(candidate.list_price) - Decimal(candidate.internal_cost), Decimal(candidate.list_price))}% "
                            f"unit margin and would lift the blended figure without "
                            f"reducing any existing discount."
                        ),
                        impact_prefix="Accepting it would add",
                        confidence="MEDIUM",
                    )
                )

        # ------------------------------------------------ 3. volume upsell
        for line in hardware:
            quantity = Decimal(line.quantity)
            target = next((t for t in VOLUME_THRESHOLDS if t > quantity), None)
            if target is None or (target - quantity) > quantity * Decimal("0.15"):
                continue
            product = await session.get(Product, line.product_id)
            if product is None:
                continue
            uplift = target - quantity
            results.append(
                cls._build(
                    kind="VOLUME_UPSELL",
                    product=product,
                    quantity=uplift,
                    reason=(
                        f"'{line.description}' is at {quantity} units, only {uplift} "
                        f"short of the {target}-unit band. Customers at that band "
                        f"typically accept the uplift in exchange for the same "
                        f"discount."
                    ),
                    impact_prefix="The extra units would add",
                    confidence="LOW",
                )
            )

        # PDF A6.2 — promoted products "rank higher in suggestions".
        results.sort(key=lambda r: (not r.is_promoted, _CONFIDENCE_RANK.get(r.confidence, 3)))
        return [r.as_dict() for r in results]

    @staticmethod
    def _best_margin_product(candidates: list[Product]) -> Product | None:
        """Highest unit-margin candidate, with promoted products preferred.

        PDF A6.2 asks promoted products to rank higher; margin ratio remains
        the tie-break so a promotion cannot surface a loss-making item.
        """
        priced = [p for p in candidates if Decimal(p.list_price) > ZERO]
        if not priced:
            return None
        return max(
            priced,
            key=lambda p: (
                bool(p.is_promoted),
                (Decimal(p.list_price) - Decimal(p.internal_cost))
                / Decimal(p.list_price),
                Decimal(p.list_price),
            ),
        )

    @staticmethod
    def _build(
        *,
        kind: str,
        product: Product,
        quantity: Decimal,
        reason: str,
        impact_prefix: str,
        confidence: str,
    ) -> Recommendation:
        calc = CommercialEngine.calculate_line(
            quantity=quantity,
            unit_list_price=Decimal(product.list_price),
            unit_cost=Decimal(product.internal_cost),
            recurring_periods=product.default_recurring_periods,
        )
        return Recommendation(
            kind=kind,
            product_id=product.id,
            product_name=product.name,
            suggested_quantity=quantity,
            estimated_revenue=calc.net_amount,
            estimated_margin=calc.line_margin,
            estimated_margin_pct=calc.line_margin_pct,
            reason=reason,
            impact=(
                f"{impact_prefix} {money(calc.net_amount)} of revenue at "
                f"{calc.line_margin_pct}% margin "
                f"({money(calc.line_margin)} gross profit)."
            ),
            confidence=confidence,
            is_promoted=bool(product.is_promoted),
            detail={
                "category": product.category.value,
                "sku": product.sku,
                "unit_list_price": str(product.list_price),
                "is_promoted": bool(product.is_promoted),
            },
        )
