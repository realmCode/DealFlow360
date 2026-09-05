"""DashboardService — Control Tower aggregation and deal health scoring.

The Control Tower is an *action queue*, not a KPI wall: it returns attention
items sorted by severity then age, grouped so an operator can work top-down.

Deal health is a deterministic penalty model, not a vibe. Every deal starts at
100 and loses points for concrete, named conditions; each deduction is returned
as a signal with its own explanation so the number is always defensible.

    CRITICAL attention item   -30 each (capped at -60)
    HIGH attention item       -15 each (capped at -30)
    MEDIUM attention item      -5 each (capped at -15)
    Margin below policy floor -20
    Stale approval present    -25
    Approval still pending    -10
    Inventory shortage        -10
    Quote issued, no reply    -10  (after 14 days)
    No quote created yet      -10

    CLOSED_WON  -> 100   CLOSED_LOST -> 0
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    ApprovalRequestStatus,
    AttentionItemStatus,
    AttentionItemType,
    DealStage,
    QuoteVersionStatus,
    SalesOrderStatus,
    SEVERITY_RANK,
    Severity,
)
from app.models.approval_request import ApprovalRequest
from app.models.attention_item import AttentionItem
from app.models.customer_profile import CustomerProfile
from app.models.deal import Deal
from app.models.quote import Quote
from app.models.quote_version import QuoteVersion
from app.models.sales_order import SalesOrder
from app.models.user import User
from app.services.audit_service import AttentionService
from app.services.commercial_engine import ZERO, money, pct
from app.services.policy_engine import _trim
from app.services.settings_service import SettingsService

#: Fallback only. The live value comes from `organization_settings`
#: (PDF B9.1 requires the window to be configured, not compiled in).
NO_RESPONSE_DAYS = 14

CAPS = {
    Severity.CRITICAL: 60,
    Severity.HIGH: 30,
    Severity.MEDIUM: 15,
    Severity.LOW: 0,
}
PER_ITEM = {
    Severity.CRITICAL: 30,
    Severity.HIGH: 15,
    Severity.MEDIUM: 5,
    Severity.LOW: 0,
}


class DashboardService:
    # ------------------------------------------------------- control tower
    @staticmethod
    async def open_items(
        session: AsyncSession,
        organization_id: uuid.UUID,
        *,
        severity: Severity | None = None,
        item_type: AttentionItemType | None = None,
        include_resolved: bool = False,
    ) -> list[AttentionItem]:
        stmt = select(AttentionItem).where(
            AttentionItem.organization_id == organization_id
        )
        if not include_resolved:
            stmt = stmt.where(AttentionItem.status != AttentionItemStatus.RESOLVED)
        if severity is not None:
            stmt = stmt.where(AttentionItem.severity == severity)
        if item_type is not None:
            stmt = stmt.where(AttentionItem.type == item_type)
        items = list((await session.execute(stmt)).scalars())
        return sorted(items, key=AttentionService.sort_key)

    @classmethod
    async def control_tower(
        cls, session: AsyncSession, user: User
    ) -> dict[str, Any]:
        items = await cls.open_items(session, user.organization_id)

        counts = {s: 0 for s in Severity}
        by_type: dict[str, int] = {}
        for item in items:
            counts[item.severity] += 1
            by_type[item.type.value] = by_type.get(item.type.value, 0) + 1

        groups = []
        for severity in sorted(Severity, key=lambda s: -SEVERITY_RANK[s]):
            bucket = [i for i in items if i.severity is severity]
            if bucket:
                groups.append(
                    {"severity": severity, "count": len(bucket), "items": bucket}
                )

        mine = [
            item
            for item in items
            if item.owner_user_id == user.id or item.owner_role == user.role_code
        ]

        if not items:
            headline = "Nothing needs your attention. Every deal is inside policy."
        else:
            top = items[0]
            headline = (
                f"{len(items)} open item(s): {counts[Severity.CRITICAL]} critical, "
                f"{counts[Severity.HIGH]} high. Most urgent: {top.title}."
            )

        return {
            "organization_id": user.organization_id,
            "generated_at": datetime.now(UTC),
            "counts": {
                "critical": counts[Severity.CRITICAL],
                "high": counts[Severity.HIGH],
                "medium": counts[Severity.MEDIUM],
                "low": counts[Severity.LOW],
                "total_open": len(items),
            },
            "by_type": by_type,
            "groups": groups,
            "my_queue": mine,
            "headline": headline,
        }

    # ---------------------------------------------------------- deal health
    @classmethod
    async def deal_health(
        cls, session: AsyncSession, organization_id: uuid.UUID, deal: Deal
    ) -> dict[str, Any]:
        profile = await session.get(CustomerProfile, deal.customer_profile_id)
        quotes = list(
            (
                await session.execute(
                    select(Quote).where(Quote.deal_id == deal.id)
                )
            ).scalars()
        )
        items = list(
            (
                await session.execute(
                    select(AttentionItem).where(
                        AttentionItem.organization_id == organization_id,
                        AttentionItem.deal_id == deal.id,
                        AttentionItem.status != AttentionItemStatus.RESOLVED,
                    )
                )
            ).scalars()
        )

        current_version: QuoteVersion | None = None
        total_value = Decimal(deal.expected_value or ZERO)
        margin_pct = ZERO
        for quote in quotes:
            version = (
                await session.execute(
                    select(QuoteVersion)
                    .where(
                        QuoteVersion.quote_id == quote.id,
                        QuoteVersion.version_number == quote.current_version_number,
                    )
                )
            ).scalars().first()
            if version is None:
                continue
            if current_version is None or version.created_at > current_version.created_at:
                current_version = version
        if current_version is not None:
            total_value = money(current_version.total_revenue)
            margin_pct = pct(current_version.margin_pct)

        signals: list[dict[str, Any]] = []
        score = 100
        blocked = False

        if deal.stage is DealStage.CLOSED_LOST:
            return cls._finalise_health(
                deal,
                profile,
                total_value,
                margin_pct,
                0,
                [
                    {
                        "code": "CLOSED_LOST",
                        "label": "Deal lost",
                        "severity": Severity.CRITICAL,
                        "detail": "The deal was closed without an order.",
                        "points": -100,
                    }
                ],
                len(items),
                blocked=False,
            )
        if deal.stage is DealStage.CLOSED_WON:
            return cls._finalise_health(
                deal,
                profile,
                total_value,
                margin_pct,
                100,
                [
                    {
                        "code": "CLOSED_WON",
                        "label": "Deal won",
                        "severity": Severity.LOW,
                        "detail": "The quote was confirmed and an order exists.",
                        "points": 0,
                    }
                ],
                len(items),
                blocked=False,
            )

        # ---------------------------------------- attention item deductions
        for severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM):
            bucket = [i for i in items if i.severity is severity]
            if not bucket:
                continue
            penalty = min(CAPS[severity], PER_ITEM[severity] * len(bucket))
            score -= penalty
            signals.append(
                {
                    "code": f"ATTENTION_{severity.value}",
                    "label": f"{len(bucket)} {severity.value.lower()} attention item(s)",
                    "severity": severity,
                    "detail": "; ".join(i.title for i in bucket[:3]),
                    "points": -penalty,
                }
            )
            if severity is Severity.CRITICAL:
                blocked = True

        if any(i.type is AttentionItemType.INVENTORY_SHORTAGE for i in items):
            score -= 10
            signals.append(
                {
                    "code": "INVENTORY_SHORTAGE",
                    "label": "Stock shortage",
                    "severity": Severity.HIGH,
                    "detail": "The order cannot be fully sourced from current stock.",
                    "points": -10,
                }
            )

        if not quotes:
            score -= 10
            signals.append(
                {
                    "code": "NO_QUOTE",
                    "label": "No quote yet",
                    "severity": Severity.MEDIUM,
                    "detail": "The deal has no quote, so nothing can progress.",
                    "points": -10,
                }
            )

        if current_version is not None:
            if margin_pct < Decimal("10") and total_value > ZERO:
                score -= 20
                signals.append(
                    {
                        "code": "LOW_MARGIN",
                        "label": "Margin below policy floor",
                        "severity": Severity.HIGH,
                        "detail": (
                            f"Current margin is {_trim(margin_pct)}%, below the 10% "
                            f"floor."
                        ),
                        "points": -20,
                    }
                )

            stale = (
                await session.execute(
                    select(func.count())
                    .select_from(ApprovalRequest)
                    .where(
                        ApprovalRequest.quote_id == current_version.quote_id,
                        ApprovalRequest.status == ApprovalRequestStatus.STALE,
                    )
                )
            ).scalar_one()
            if current_version.is_stale or int(stale) > 0:
                score -= 25
                blocked = True
                signals.append(
                    {
                        "code": "STALE_APPROVAL",
                        "label": "Approval invalidated",
                        "severity": Severity.CRITICAL,
                        "detail": (
                            current_version.stale_reason
                            or "A material change invalidated a prior approval."
                        ),
                        "points": -25,
                    }
                )

            pending = (
                await session.execute(
                    select(func.count())
                    .select_from(ApprovalRequest)
                    .where(
                        ApprovalRequest.quote_version_id == current_version.id,
                        ApprovalRequest.status == ApprovalRequestStatus.PENDING,
                    )
                )
            ).scalar_one()
            if int(pending) > 0:
                score -= 10
                blocked = True
                signals.append(
                    {
                        "code": "PENDING_APPROVAL",
                        "label": "Awaiting approval",
                        "severity": Severity.MEDIUM,
                        "detail": "The current version cannot be sent until approved.",
                        "points": -10,
                    }
                )

            # PDF B9.1 — "inactive for more than a configured number of days".
            # The window is per-organization rather than a module constant, so
            # two tenants on one deployment can disagree about what stalled
            # means for their sales cycle.
            stalled_days = await SettingsService.stalled_deal_days(
                session, organization_id
            )
            if (
                current_version.status is QuoteVersionStatus.SENT
                and current_version.sent_at is not None
                and current_version.sent_at
                < datetime.now(UTC) - timedelta(days=stalled_days)
            ):
                score -= 10
                signals.append(
                    {
                        "code": "NO_CUSTOMER_RESPONSE",
                        "label": "Customer silent",
                        "severity": Severity.MEDIUM,
                        "detail": (
                            f"Sent {current_version.sent_at.date().isoformat()} with "
                            f"no reply for over {stalled_days} days."
                        ),
                        "points": -10,
                    }
                )

            anomaly_items = [
                i
                for i in items
                if i.type is AttentionItemType.DISCOUNT_ANOMALY
            ]
            if anomaly_items:
                score -= 10
                signals.append(
                    {
                        "code": "DISCOUNT_ANOMALY",
                        "label": "Unusual discount",
                        "severity": anomaly_items[0].severity,
                        "detail": anomaly_items[0].reason,
                        "points": -10,
                    }
                )

        # PDF B9.3 — delivery promise slippage.
        late_order = (
            await session.execute(
                select(SalesOrder)
                .where(
                    SalesOrder.deal_id == deal.id,
                    SalesOrder.promised_delivery_date.is_not(None),
                    SalesOrder.promised_delivery_date < datetime.now(UTC).date(),
                    SalesOrder.fulfilled_at.is_(None),
                    SalesOrder.status != SalesOrderStatus.CANCELLED,
                )
                .limit(1)
            )
        ).scalars().first()
        if late_order is not None:
            days_late = (
                datetime.now(UTC).date() - late_order.promised_delivery_date
            ).days
            score -= 15
            signals.append(
                {
                    "code": "DELIVERY_SLIPPAGE",
                    "label": "Delivery promise missed",
                    "severity": (
                        Severity.HIGH if days_late > 7 else Severity.MEDIUM
                    ),
                    "detail": (
                        f"Order {late_order.order_number} was promised "
                        f"{late_order.promised_delivery_date.isoformat()} and is "
                        f"{days_late} day(s) late with no fulfilment recorded."
                    ),
                    "points": -15,
                }
            )

        if not signals:
            signals.append(
                {
                    "code": "HEALTHY",
                    "label": "On track",
                    "severity": Severity.LOW,
                    "detail": "No policy breaches, no blockers, no stale decisions.",
                    "points": 0,
                }
            )

        return cls._finalise_health(
            deal,
            profile,
            total_value,
            margin_pct,
            max(0, min(100, score)),
            signals,
            len(items),
            blocked=blocked,
        )

    @staticmethod
    def _band(score: int) -> str:
        if score >= 80:
            return "HEALTHY"
        if score >= 60:
            return "WATCH"
        if score >= 40:
            return "AT_RISK"
        return "CRITICAL"

    @classmethod
    def _finalise_health(
        cls,
        deal: Deal,
        profile: CustomerProfile | None,
        total_value: Decimal,
        margin_pct: Decimal,
        score: int,
        signals: list[dict[str, Any]],
        open_items: int,
        *,
        blocked: bool,
    ) -> dict[str, Any]:
        band = cls._band(score)
        worst = max(signals, key=lambda s: SEVERITY_RANK[s["severity"]])
        summary = (
            f"{deal.reference} scores {score}/100 ({band}). "
            f"{'Blocked: ' if blocked else ''}{worst['detail']}"
        )
        return {
            "deal_id": deal.id,
            "deal_reference": deal.reference,
            "deal_name": deal.name,
            "customer_name": profile.display_name if profile else "Unknown",
            "stage": deal.stage,
            "health_score": score,
            "health_band": band,
            "total_value": total_value,
            "margin_pct": margin_pct,
            "blocked": blocked,
            "signals": signals,
            "open_attention_items": open_items,
            "summary": summary,
        }

    @classmethod
    async def deal_health_list(
        cls, session: AsyncSession, organization_id: uuid.UUID
    ) -> dict[str, Any]:
        deals = list(
            (
                await session.execute(
                    select(Deal)
                    .where(Deal.organization_id == organization_id)
                    .order_by(Deal.created_at.desc())
                )
            ).scalars()
        )
        entries = [
            await cls.deal_health(session, organization_id, deal) for deal in deals
        ]
        entries.sort(key=lambda e: e["health_score"])
        average = (
            int(sum(e["health_score"] for e in entries) / len(entries))
            if entries
            else 100
        )
        return {
            "generated_at": datetime.now(UTC),
            "average_health": average,
            "deals": entries,
        }
