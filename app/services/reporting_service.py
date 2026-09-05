"""Sales performance reporting — PDF module A7.

The Control Tower in `dashboard_service` answers "what needs my attention right
now". This module answers a different question: "how are we performing, sliced
by period, team, rep, approval status and product". They are not the same
artifact and one cannot substitute for the other.

Every aggregate is computed in SQL rather than by loading rows and summing in
Python. That is not premature optimisation — a report over a year of orders
would otherwise pull the entire order book into memory to produce twenty
numbers.

All four PDF A7 filters are supported everywhere they make sense:

    Period            -> PeriodParams (shared with the list endpoints)
    Sales Team / Rep  -> team_id / rep_user_id
    Approval Status   -> approval_status
    Product/Category  -> product_id / category
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Sequence

import sqlalchemy as sa
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    ApprovalRequestStatus,
    DealStage,
    ProductCategory,
    QuoteVersionStatus,
    SalesOrderStatus,
)
from app.models.approval_request import ApprovalRequest
from app.models.customer_profile import CustomerProfile
from app.models.deal import Deal
from app.models.product import Product
from app.models.quote import Quote
from app.models.quote_version import QuoteVersion
from app.models.sales_order import SalesOrder
from app.models.sales_order_line import SalesOrderLine
from app.models.sales_team import SalesTeamMember
from app.models.user import User
from app.schemas.query import PeriodParams
from app.services.commercial_engine import ZERO, money, pct, safe_pct


@dataclass(slots=True)
class ReportFilters:
    """The A7 filter set, resolved once and applied consistently."""

    organization_id: uuid.UUID
    period: PeriodParams
    rep_user_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    approval_status: ApprovalRequestStatus | None = None
    product_id: uuid.UUID | None = None
    category: ProductCategory | None = None
    customer_profile_id: uuid.UUID | None = None

    def describe(self) -> dict[str, Any]:
        """Echo the applied filters so an exported report is self-describing."""
        return {
            "period": self.period.describe(),
            "date_from": (
                self.period.date_from.isoformat() if self.period.date_from else None
            ),
            "date_to": (
                self.period.date_to.isoformat() if self.period.date_to else None
            ),
            "rep_user_id": str(self.rep_user_id) if self.rep_user_id else None,
            "team_id": str(self.team_id) if self.team_id else None,
            "approval_status": (
                self.approval_status.value if self.approval_status else None
            ),
            "product_id": str(self.product_id) if self.product_id else None,
            "category": self.category.value if self.category else None,
            "customer_profile_id": (
                str(self.customer_profile_id) if self.customer_profile_id else None
            ),
        }


@dataclass(slots=True)
class ReportRow:
    key: str
    label: str
    values: dict[str, Any] = field(default_factory=dict)


class ReportingService:
    # ------------------------------------------------------------- helpers
    @staticmethod
    def _team_member_subquery(team_id: uuid.UUID) -> Select[Any]:
        return select(SalesTeamMember.user_id).where(
            SalesTeamMember.sales_team_id == team_id
        )

    @classmethod
    def _apply_deal_scope(
        cls, stmt: Select[Any], filters: ReportFilters
    ) -> Select[Any]:
        """Rep, team and customer filters all resolve through the deal owner."""
        if filters.rep_user_id is not None:
            stmt = stmt.where(Deal.owner_user_id == filters.rep_user_id)
        if filters.team_id is not None:
            stmt = stmt.where(
                Deal.owner_user_id.in_(cls._team_member_subquery(filters.team_id))
            )
        if filters.customer_profile_id is not None:
            stmt = stmt.where(
                Deal.customer_profile_id == filters.customer_profile_id
            )
        return stmt

    @staticmethod
    def _apply_period(
        stmt: Select[Any], filters: ReportFilters, column: Any
    ) -> Select[Any]:
        if filters.period.start_at is not None:
            stmt = stmt.where(column >= filters.period.start_at)
        if filters.period.end_at is not None:
            stmt = stmt.where(column < filters.period.end_at)
        return stmt

    # -------------------------------------------------- sales performance
    @classmethod
    async def sales_performance(
        cls,
        session: AsyncSession,
        filters: ReportFilters,
        *,
        group_by: str = "rep",
    ) -> dict[str, Any]:
        """Revenue, margin, discount and win rate, grouped as requested.

        Measured over **quote versions**, because a quote that was discounted
        and lost is exactly as informative about discounting behaviour as one
        that was won — restricting to orders would hide the losses.
        """
        grouping = cls._performance_grouping(group_by)

        stmt = (
            select(
                grouping["key"].label("group_key"),
                grouping["label"].label("group_label"),
                func.count(sa.distinct(QuoteVersion.id)).label("version_count"),
                func.count(sa.distinct(Quote.id)).label("quote_count"),
                func.coalesce(func.sum(QuoteVersion.gross_revenue), 0).label("gross"),
                func.coalesce(func.sum(QuoteVersion.total_discount), 0).label(
                    "discount"
                ),
                func.coalesce(func.sum(QuoteVersion.net_revenue), 0).label("net"),
                func.coalesce(func.sum(QuoteVersion.total_cost), 0).label("cost"),
                func.coalesce(func.sum(QuoteVersion.margin), 0).label("margin"),
                func.coalesce(func.avg(QuoteVersion.effective_discount_pct), 0).label(
                    "avg_discount_pct"
                ),
                func.coalesce(func.avg(QuoteVersion.blended_risk_score), 0).label(
                    "avg_risk"
                ),
                func.count(
                    sa.distinct(
                        sa.case(
                            (
                                QuoteVersion.status == QuoteVersionStatus.CONFIRMED,
                                Quote.id,
                            ),
                            else_=None,
                        )
                    )
                ).label("won_count"),
                func.count(
                    sa.distinct(
                        sa.case(
                            (
                                QuoteVersion.status == QuoteVersionStatus.REJECTED,
                                Quote.id,
                            ),
                            else_=None,
                        )
                    )
                ).label("lost_count"),
            )
            .select_from(QuoteVersion)
            .join(Quote, Quote.id == QuoteVersion.quote_id)
            .join(Deal, Deal.id == Quote.deal_id)
            .join(CustomerProfile, CustomerProfile.id == Deal.customer_profile_id)
            .outerjoin(User, User.id == Deal.owner_user_id)
            .where(QuoteVersion.organization_id == filters.organization_id)
            .group_by(grouping["key"], grouping["label"])
        )
        stmt = cls._apply_deal_scope(stmt, filters)
        stmt = cls._apply_period(stmt, filters, QuoteVersion.created_at)

        if filters.approval_status is not None:
            stmt = stmt.where(
                QuoteVersion.id.in_(
                    select(ApprovalRequest.quote_version_id).where(
                        ApprovalRequest.organization_id == filters.organization_id,
                        ApprovalRequest.status == filters.approval_status,
                    )
                )
            )
        if filters.product_id is not None or filters.category is not None:
            from app.models.quote_line import QuoteLine

            line_stmt = select(QuoteLine.quote_version_id)
            if filters.product_id is not None:
                line_stmt = line_stmt.where(QuoteLine.product_id == filters.product_id)
            if filters.category is not None:
                line_stmt = line_stmt.where(QuoteLine.category == filters.category)
            stmt = stmt.where(QuoteVersion.id.in_(line_stmt))

        rows = (await session.execute(stmt)).all()

        entries: list[dict[str, Any]] = []
        totals = {
            "gross": ZERO,
            "discount": ZERO,
            "net": ZERO,
            "cost": ZERO,
            "margin": ZERO,
            "quote_count": 0,
            "won_count": 0,
            "lost_count": 0,
        }

        for row in rows:
            decided = int(row.won_count) + int(row.lost_count)
            entries.append(
                {
                    "group_key": str(row.group_key) if row.group_key else "unassigned",
                    "group_label": row.group_label or "Unassigned",
                    "quote_count": int(row.quote_count),
                    "version_count": int(row.version_count),
                    "gross_revenue": str(money(Decimal(row.gross))),
                    "total_discount": str(money(Decimal(row.discount))),
                    "net_revenue": str(money(Decimal(row.net))),
                    "total_cost": str(money(Decimal(row.cost))),
                    "margin": str(money(Decimal(row.margin))),
                    "margin_pct": str(
                        safe_pct(Decimal(row.margin), Decimal(row.net))
                    ),
                    "avg_discount_pct": str(pct(Decimal(row.avg_discount_pct))),
                    "avg_blended_risk": str(pct(Decimal(row.avg_risk))),
                    "won_count": int(row.won_count),
                    "lost_count": int(row.lost_count),
                    "win_rate_pct": str(
                        safe_pct(Decimal(row.won_count), Decimal(decided))
                        if decided
                        else pct(ZERO)
                    ),
                }
            )
            totals["gross"] += Decimal(row.gross)
            totals["discount"] += Decimal(row.discount)
            totals["net"] += Decimal(row.net)
            totals["cost"] += Decimal(row.cost)
            totals["margin"] += Decimal(row.margin)
            totals["quote_count"] += int(row.quote_count)
            totals["won_count"] += int(row.won_count)
            totals["lost_count"] += int(row.lost_count)

        entries.sort(key=lambda e: Decimal(e["net_revenue"]), reverse=True)
        decided_total = totals["won_count"] + totals["lost_count"]

        return {
            "group_by": group_by,
            "filters": filters.describe(),
            "rows": entries,
            "totals": {
                "quote_count": totals["quote_count"],
                "gross_revenue": str(money(totals["gross"])),
                "total_discount": str(money(totals["discount"])),
                "net_revenue": str(money(totals["net"])),
                "total_cost": str(money(totals["cost"])),
                "margin": str(money(totals["margin"])),
                "margin_pct": str(safe_pct(totals["margin"], totals["net"])),
                "effective_discount_pct": str(
                    safe_pct(totals["discount"], totals["gross"])
                ),
                "won_count": totals["won_count"],
                "lost_count": totals["lost_count"],
                "win_rate_pct": str(
                    safe_pct(Decimal(totals["won_count"]), Decimal(decided_total))
                    if decided_total
                    else pct(ZERO)
                ),
            },
        }

    @staticmethod
    def _performance_grouping(group_by: str) -> dict[str, Any]:
        from app.errors import ValidationError

        options: dict[str, dict[str, Any]] = {
            "rep": {"key": Deal.owner_user_id, "label": User.full_name},
            "customer": {
                "key": Deal.customer_profile_id,
                "label": CustomerProfile.display_name,
            },
            "tier": {"key": CustomerProfile.tier, "label": CustomerProfile.tier},
            "stage": {"key": Deal.stage, "label": Deal.stage},
            "status": {"key": QuoteVersion.status, "label": QuoteVersion.status},
            "month": {
                "key": func.to_char(QuoteVersion.created_at, "YYYY-MM"),
                "label": func.to_char(QuoteVersion.created_at, "YYYY-MM"),
            },
            "risk_band": {
                "key": QuoteVersion.risk_band,
                "label": QuoteVersion.risk_band,
            },
        }
        if group_by not in options:
            raise ValidationError(
                f"Cannot group by {group_by!r}.",
                code="INVALID_GROUP_BY",
                details={"group_by": group_by, "allowed": sorted(options)},
            )
        return options[group_by]

    # ---------------------------------------------------- approval status
    @classmethod
    async def approval_status(
        cls, session: AsyncSession, filters: ReportFilters
    ) -> dict[str, Any]:
        """Counts, value and time-to-decision per approval state (A7.5)."""
        stmt = (
            select(
                ApprovalRequest.status,
                func.count(ApprovalRequest.id).label("count"),
                func.coalesce(func.sum(QuoteVersion.total_revenue), 0).label("value"),
                func.coalesce(func.avg(ApprovalRequest.blended_risk_score), 0).label(
                    "avg_risk"
                ),
                func.coalesce(
                    func.avg(
                        sa.extract(
                            "epoch",
                            ApprovalRequest.decided_at - ApprovalRequest.created_at,
                        )
                    ),
                    0,
                ).label("avg_seconds_to_decide"),
            )
            .select_from(ApprovalRequest)
            .join(QuoteVersion, QuoteVersion.id == ApprovalRequest.quote_version_id)
            .join(Quote, Quote.id == ApprovalRequest.quote_id)
            .join(Deal, Deal.id == Quote.deal_id)
            .where(ApprovalRequest.organization_id == filters.organization_id)
            .group_by(ApprovalRequest.status)
        )
        stmt = cls._apply_deal_scope(stmt, filters)
        stmt = cls._apply_period(stmt, filters, ApprovalRequest.created_at)
        if filters.approval_status is not None:
            stmt = stmt.where(ApprovalRequest.status == filters.approval_status)

        rows = (await session.execute(stmt)).all()
        by_status = {
            row.status.value: {
                "count": int(row.count),
                "total_value": str(money(Decimal(row.value))),
                "avg_blended_risk": str(pct(Decimal(row.avg_risk))),
                "avg_hours_to_decision": (
                    str(pct(Decimal(row.avg_seconds_to_decide) / Decimal(3600)))
                    if row.avg_seconds_to_decide
                    else None
                ),
            }
            for row in rows
        }
        # Report every state, including the ones with no rows: a zero is a
        # meaningful answer and an absent key forces the client to guess.
        for status in ApprovalRequestStatus:
            by_status.setdefault(
                status.value,
                {
                    "count": 0,
                    "total_value": "0.00",
                    "avg_blended_risk": "0.0000",
                    "avg_hours_to_decision": None,
                },
            )

        return {
            "filters": filters.describe(),
            "by_status": by_status,
            "total_requests": sum(v["count"] for v in by_status.values()),
        }

    # ---------------------------------------------------------- products
    @classmethod
    async def products(
        cls, session: AsyncSession, filters: ReportFilters, *, limit: int = 25
    ) -> dict[str, Any]:
        """Best-selling and most-discounted products (A7.6)."""
        stmt = (
            select(
                Product.id,
                Product.sku,
                Product.name,
                Product.category,
                func.coalesce(func.sum(SalesOrderLine.quantity), 0).label("units"),
                func.coalesce(func.sum(SalesOrderLine.net_amount), 0).label("revenue"),
                func.coalesce(func.sum(SalesOrderLine.line_cost), 0).label("cost"),
                func.coalesce(func.sum(SalesOrderLine.discount_amount), 0).label(
                    "discount"
                ),
                func.coalesce(func.avg(SalesOrderLine.discount_pct), 0).label(
                    "avg_discount_pct"
                ),
                func.count(sa.distinct(SalesOrderLine.sales_order_id)).label(
                    "order_count"
                ),
            )
            .select_from(SalesOrderLine)
            .join(Product, Product.id == SalesOrderLine.product_id)
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .join(Deal, Deal.id == SalesOrder.deal_id)
            .where(
                SalesOrderLine.organization_id == filters.organization_id,
                SalesOrder.status != SalesOrderStatus.CANCELLED,
            )
            .group_by(Product.id, Product.sku, Product.name, Product.category)
        )
        stmt = cls._apply_deal_scope(stmt, filters)
        stmt = cls._apply_period(stmt, filters, SalesOrder.confirmed_at)
        if filters.product_id is not None:
            stmt = stmt.where(Product.id == filters.product_id)
        if filters.category is not None:
            stmt = stmt.where(Product.category == filters.category)

        rows = (await session.execute(stmt)).all()
        entries = [
            {
                "product_id": str(row.id),
                "sku": row.sku,
                "name": row.name,
                "category": row.category.value,
                "units_sold": str(Decimal(row.units)),
                "order_count": int(row.order_count),
                "net_revenue": str(money(Decimal(row.revenue))),
                "total_cost": str(money(Decimal(row.cost))),
                "margin": str(money(Decimal(row.revenue) - Decimal(row.cost))),
                "margin_pct": str(
                    safe_pct(
                        Decimal(row.revenue) - Decimal(row.cost), Decimal(row.revenue)
                    )
                ),
                "total_discount_given": str(money(Decimal(row.discount))),
                "avg_discount_pct": str(pct(Decimal(row.avg_discount_pct))),
            }
            for row in rows
        ]

        best_selling = sorted(
            entries, key=lambda e: Decimal(e["net_revenue"]), reverse=True
        )[:limit]
        most_discounted = sorted(
            entries, key=lambda e: Decimal(e["avg_discount_pct"]), reverse=True
        )[:limit]
        by_margin = sorted(
            entries, key=lambda e: Decimal(e["margin"]), reverse=True
        )[:limit]

        return {
            "filters": filters.describe(),
            "best_selling": best_selling,
            "most_discounted": most_discounted,
            "highest_margin_contribution": by_margin,
            "product_count": len(entries),
        }

    # --------------------------------------------------------- discounts
    @classmethod
    async def discounts(
        cls, session: AsyncSession, filters: ReportFilters
    ) -> dict[str, Any]:
        """Discount distribution per rep, plus ceiling-breach frequency (A7.6/B9.2)."""
        stmt = (
            select(
                Deal.owner_user_id.label("rep_id"),
                User.full_name.label("rep_name"),
                func.count(QuoteVersion.id).label("version_count"),
                func.coalesce(func.avg(QuoteVersion.effective_discount_pct), 0).label(
                    "avg_discount"
                ),
                func.coalesce(func.max(QuoteVersion.effective_discount_pct), 0).label(
                    "max_discount"
                ),
                func.coalesce(func.min(QuoteVersion.effective_discount_pct), 0).label(
                    "min_discount"
                ),
                func.coalesce(
                    func.stddev_samp(QuoteVersion.effective_discount_pct), 0
                ).label("stdev_discount"),
                func.coalesce(func.sum(QuoteVersion.total_discount), 0).label(
                    "total_given"
                ),
                func.coalesce(func.avg(QuoteVersion.margin_pct), 0).label("avg_margin"),
                func.count(
                    sa.case((QuoteVersion.requires_approval.is_(True), 1), else_=None)
                ).label("needed_approval"),
            )
            .select_from(QuoteVersion)
            .join(Quote, Quote.id == QuoteVersion.quote_id)
            .join(Deal, Deal.id == Quote.deal_id)
            .outerjoin(User, User.id == Deal.owner_user_id)
            .where(
                QuoteVersion.organization_id == filters.organization_id,
                QuoteVersion.status != QuoteVersionStatus.DRAFT,
            )
            .group_by(Deal.owner_user_id, User.full_name)
        )
        stmt = cls._apply_deal_scope(stmt, filters)
        stmt = cls._apply_period(stmt, filters, QuoteVersion.created_at)

        rows = (await session.execute(stmt)).all()
        by_rep = [
            {
                "rep_user_id": str(row.rep_id) if row.rep_id else None,
                "rep_name": row.rep_name or "Unassigned",
                "version_count": int(row.version_count),
                "avg_discount_pct": str(pct(Decimal(row.avg_discount))),
                "min_discount_pct": str(pct(Decimal(row.min_discount))),
                "max_discount_pct": str(pct(Decimal(row.max_discount))),
                "stdev_discount_pct": str(pct(Decimal(row.stdev_discount))),
                "total_discount_given": str(money(Decimal(row.total_given))),
                "avg_margin_pct": str(pct(Decimal(row.avg_margin))),
                "required_approval_count": int(row.needed_approval),
            }
            for row in rows
        ]
        by_rep.sort(key=lambda r: Decimal(r["avg_discount_pct"]), reverse=True)

        histogram = await cls._discount_histogram(session, filters)
        return {
            "filters": filters.describe(),
            "by_rep": by_rep,
            "distribution": histogram,
        }

    @classmethod
    async def _discount_histogram(
        cls, session: AsyncSession, filters: ReportFilters
    ) -> list[dict[str, Any]]:
        bands = (
            ("0", ZERO, Decimal("0.0001")),
            ("0-5", Decimal("0.0001"), Decimal("5")),
            ("5-10", Decimal("5"), Decimal("10")),
            ("10-15", Decimal("10"), Decimal("15")),
            ("15-20", Decimal("15"), Decimal("20")),
            ("20-30", Decimal("20"), Decimal("30")),
            ("30+", Decimal("30"), Decimal("1000")),
        )
        case_expr = sa.case(
            *[
                (
                    sa.and_(
                        QuoteVersion.effective_discount_pct >= low,
                        QuoteVersion.effective_discount_pct < high,
                    ),
                    label,
                )
                for label, low, high in bands
            ],
            else_="unknown",
        )
        stmt = (
            select(case_expr.label("band"), func.count(QuoteVersion.id).label("count"))
            .select_from(QuoteVersion)
            .join(Quote, Quote.id == QuoteVersion.quote_id)
            .join(Deal, Deal.id == Quote.deal_id)
            .where(
                QuoteVersion.organization_id == filters.organization_id,
                QuoteVersion.status != QuoteVersionStatus.DRAFT,
            )
            .group_by(case_expr)
        )
        stmt = cls._apply_deal_scope(stmt, filters)
        stmt = cls._apply_period(stmt, filters, QuoteVersion.created_at)
        rows = {r.band: int(r.count) for r in (await session.execute(stmt)).all()}
        return [
            {"band": label, "count": rows.get(label, 0)} for label, _l, _h in bands
        ]

    # ----------------------------------------------------------- pipeline
    @classmethod
    async def pipeline(
        cls, session: AsyncSession, filters: ReportFilters
    ) -> dict[str, Any]:
        """Deal count and value by stage (A7.1)."""
        stmt = (
            select(
                Deal.stage,
                func.count(Deal.id).label("count"),
                func.coalesce(func.sum(Deal.expected_value), 0).label("value"),
            )
            .select_from(Deal)
            .where(Deal.organization_id == filters.organization_id)
            .group_by(Deal.stage)
        )
        stmt = cls._apply_deal_scope(stmt, filters)
        stmt = cls._apply_period(stmt, filters, Deal.created_at)

        rows = (await session.execute(stmt)).all()
        by_stage = {
            row.stage.value: {
                "count": int(row.count),
                "expected_value": str(money(Decimal(row.value))),
            }
            for row in rows
        }
        for stage in DealStage:
            by_stage.setdefault(
                stage.value, {"count": 0, "expected_value": "0.00"}
            )

        won = by_stage[DealStage.CLOSED_WON.value]["count"]
        lost = by_stage[DealStage.CLOSED_LOST.value]["count"]
        closed = won + lost
        return {
            "filters": filters.describe(),
            "by_stage": by_stage,
            "total_deals": sum(v["count"] for v in by_stage.values()),
            "won_count": won,
            "lost_count": lost,
            "win_rate_pct": str(
                safe_pct(Decimal(won), Decimal(closed)) if closed else pct(ZERO)
            ),
        }

    # ------------------------------------------------- flat export tables
    #
    # Export needs a rectangular table, not a nested document. Rather than
    # teach the exporter about every report's shape, each report exposes one
    # flattening function and the exporter stays generic.
    @staticmethod
    def flatten(report_name: str, payload: dict[str, Any]) -> tuple[
        Sequence[str], list[dict[str, Any]]
    ]:
        if report_name == "sales-performance":
            rows = payload["rows"]
            headers = [
                "group_label",
                "quote_count",
                "gross_revenue",
                "total_discount",
                "net_revenue",
                "total_cost",
                "margin",
                "margin_pct",
                "avg_discount_pct",
                "avg_blended_risk",
                "won_count",
                "lost_count",
                "win_rate_pct",
            ]
            return headers, rows

        if report_name == "approval-status":
            headers = [
                "status",
                "count",
                "total_value",
                "avg_blended_risk",
                "avg_hours_to_decision",
            ]
            rows = [
                {"status": status, **values}
                for status, values in payload["by_status"].items()
            ]
            return headers, rows

        if report_name == "products":
            headers = [
                "sku",
                "name",
                "category",
                "units_sold",
                "order_count",
                "net_revenue",
                "margin",
                "margin_pct",
                "total_discount_given",
                "avg_discount_pct",
            ]
            return headers, payload["best_selling"]

        if report_name == "discounts":
            headers = [
                "rep_name",
                "version_count",
                "avg_discount_pct",
                "min_discount_pct",
                "max_discount_pct",
                "stdev_discount_pct",
                "total_discount_given",
                "avg_margin_pct",
                "required_approval_count",
            ]
            return headers, payload["by_rep"]

        if report_name == "pipeline":
            headers = ["stage", "count", "expected_value"]
            rows = [
                {"stage": stage, **values}
                for stage, values in payload["by_stage"].items()
            ]
            return headers, rows

        from app.errors import ValidationError

        raise ValidationError(
            f"Unknown report {report_name!r}.",
            code="UNKNOWN_REPORT",
            details={"report": report_name},
        )
