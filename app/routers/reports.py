"""Reporting endpoints — PDF module A7.

Every report supports the four filters A7 names (Period, Sales Team / Rep,
Approval Status, Product / Category) and every one can be exported as
CSV, XLSX or PDF.

Read-only throughout: reports never mutate state, so they are open to all
internal roles. Nothing here is reachable by a portal user.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy import select

from app.dependencies import DbSession, InternalUser
from app.enums import ApprovalRequestStatus, ProductCategory
from app.errors import NotFoundError
from app.models.customer_profile import CustomerProfile
from app.models.deal import Deal
from app.models.quote import Quote
from app.models.quote_version import QuoteVersion
from app.models.user import User
from app.schemas.query import PeriodFilter
from app.schemas.reporting import (
    ApprovalStatusReport,
    DiscountAnomalyList,
    DiscountReport,
    PipelineReport,
    ProductReport,
    SalesPerformanceReport,
)
from app.services.anomaly_service import AnomalyService
from app.services.export_service import SUPPORTED_FORMATS, ExportService
from app.services.reporting_service import ReportFilters, ReportingService

router = APIRouter(prefix="/reports", tags=["reports"])

ExportFormat = Literal["csv", "xlsx", "pdf"]

#: Group-by options for the sales performance report.
GroupBy = Literal["rep", "customer", "tier", "stage", "status", "month", "risk_band"]


async def _filters(
    user: User,
    period: PeriodFilter,
    *,
    rep_user_id: uuid.UUID | None = None,
    team_id: uuid.UUID | None = None,
    approval_status: ApprovalRequestStatus | None = None,
    product_id: uuid.UUID | None = None,
    category: ProductCategory | None = None,
    customer_profile_id: uuid.UUID | None = None,
) -> ReportFilters:
    return ReportFilters(
        organization_id=user.organization_id,
        period=period,
        rep_user_id=rep_user_id,
        team_id=team_id,
        approval_status=approval_status,
        product_id=product_id,
        category=category,
        customer_profile_id=customer_profile_id,
    )


# ------------------------------------------------------------------ reports
@router.get(
    "/sales-performance",
    response_model=SalesPerformanceReport,
    summary="Revenue, margin, discount and win rate, grouped and filtered",
)
async def sales_performance(
    user: InternalUser,
    db: DbSession,
    period: PeriodFilter,
    group_by: Annotated[GroupBy, Query()] = "rep",
    rep_user_id: uuid.UUID | None = Query(default=None),
    team_id: uuid.UUID | None = Query(default=None),
    approval_status: ApprovalRequestStatus | None = Query(default=None),
    product_id: uuid.UUID | None = Query(default=None),
    category: ProductCategory | None = Query(default=None),
    customer_profile_id: uuid.UUID | None = Query(default=None),
) -> SalesPerformanceReport:
    filters = await _filters(
        user,
        period,
        rep_user_id=rep_user_id,
        team_id=team_id,
        approval_status=approval_status,
        product_id=product_id,
        category=category,
        customer_profile_id=customer_profile_id,
    )
    return SalesPerformanceReport.model_validate(
        await ReportingService.sales_performance(db, filters, group_by=group_by)
    )


@router.get(
    "/approval-status",
    response_model=ApprovalStatusReport,
    summary="Approval pipeline by state, with time-to-decision",
)
async def approval_status_report(
    user: InternalUser,
    db: DbSession,
    period: PeriodFilter,
    rep_user_id: uuid.UUID | None = Query(default=None),
    team_id: uuid.UUID | None = Query(default=None),
    approval_status: ApprovalRequestStatus | None = Query(default=None),
) -> ApprovalStatusReport:
    filters = await _filters(
        user,
        period,
        rep_user_id=rep_user_id,
        team_id=team_id,
        approval_status=approval_status,
    )
    return ApprovalStatusReport.model_validate(
        await ReportingService.approval_status(db, filters)
    )


@router.get(
    "/products",
    response_model=ProductReport,
    summary="Best-selling and most-discounted products",
)
async def product_report(
    user: InternalUser,
    db: DbSession,
    period: PeriodFilter,
    limit: int = Query(default=25, ge=1, le=200),
    rep_user_id: uuid.UUID | None = Query(default=None),
    team_id: uuid.UUID | None = Query(default=None),
    product_id: uuid.UUID | None = Query(default=None),
    category: ProductCategory | None = Query(default=None),
    customer_profile_id: uuid.UUID | None = Query(default=None),
) -> ProductReport:
    filters = await _filters(
        user,
        period,
        rep_user_id=rep_user_id,
        team_id=team_id,
        product_id=product_id,
        category=category,
        customer_profile_id=customer_profile_id,
    )
    return ProductReport.model_validate(
        await ReportingService.products(db, filters, limit=limit)
    )


@router.get(
    "/discounts",
    response_model=DiscountReport,
    summary="Discount distribution per rep, with a band histogram",
)
async def discount_report(
    user: InternalUser,
    db: DbSession,
    period: PeriodFilter,
    rep_user_id: uuid.UUID | None = Query(default=None),
    team_id: uuid.UUID | None = Query(default=None),
    customer_profile_id: uuid.UUID | None = Query(default=None),
) -> DiscountReport:
    filters = await _filters(
        user,
        period,
        rep_user_id=rep_user_id,
        team_id=team_id,
        customer_profile_id=customer_profile_id,
    )
    return DiscountReport.model_validate(
        await ReportingService.discounts(db, filters)
    )


@router.get(
    "/pipeline",
    response_model=PipelineReport,
    summary="Deal count and value by stage",
)
async def pipeline_report(
    user: InternalUser,
    db: DbSession,
    period: PeriodFilter,
    rep_user_id: uuid.UUID | None = Query(default=None),
    team_id: uuid.UUID | None = Query(default=None),
) -> PipelineReport:
    filters = await _filters(
        user, period, rep_user_id=rep_user_id, team_id=team_id
    )
    return PipelineReport.model_validate(
        await ReportingService.pipeline(db, filters)
    )


# ------------------------------------------------------- discount anomalies
@router.get(
    "/discount-anomalies",
    response_model=DiscountAnomalyList,
    summary="Quotes discounted well above the rep's own historical average",
)
async def discount_anomalies(
    user: InternalUser,
    db: DbSession,
    period: PeriodFilter,
    rep_user_id: uuid.UUID | None = Query(default=None),
    include_normal: bool = Query(
        default=False,
        description="Include versions that were checked and found normal.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
) -> DiscountAnomalyList:
    """PDF B9.2.

    Evaluated on read rather than served from a cache so a change to the sigma
    threshold takes effect immediately, and so a reviewer can see the current
    verdict rather than the one that happened to be stored at submit time.
    """
    stmt = (
        select(QuoteVersion, Quote, CustomerProfile, User)
        .join(Quote, Quote.id == QuoteVersion.quote_id)
        .join(Deal, Deal.id == Quote.deal_id)
        .join(CustomerProfile, CustomerProfile.id == Deal.customer_profile_id)
        .outerjoin(User, User.id == QuoteVersion.created_by_user_id)
        .where(
            QuoteVersion.organization_id == user.organization_id,
            QuoteVersion.status != "DRAFT",
        )
        .order_by(QuoteVersion.created_at.desc())
        .limit(limit)
    )
    if rep_user_id is not None:
        stmt = stmt.where(QuoteVersion.created_by_user_id == rep_user_id)
    if period.start_at is not None:
        stmt = stmt.where(QuoteVersion.created_at >= period.start_at)
    if period.end_at is not None:
        stmt = stmt.where(QuoteVersion.created_at < period.end_at)

    items: list[dict[str, Any]] = []
    for version, quote, profile, author in (await db.execute(stmt)).all():
        verdict = await AnomalyService.evaluate(
            db,
            version=version,
            actor_name=author.full_name if author else None,
        )
        if not verdict.is_anomaly and not include_normal:
            continue
        items.append(
            {
                "quote_id": quote.id,
                "quote_version_id": version.id,
                "quote_number": quote.quote_number,
                "version_number": version.version_number,
                "customer_name": profile.display_name if profile else None,
                "rep_user_id": version.created_by_user_id,
                "rep_name": author.full_name if author else None,
                "created_at": version.created_at,
                **verdict.as_dict(),
            }
        )

    return DiscountAnomalyList.model_validate(
        {
            "generated_at": datetime.now(UTC),
            "anomaly_count": sum(1 for i in items if i["is_anomaly"]),
            "items": items,
        }
    )


# ------------------------------------------------------------------ export
@router.get(
    "/{report_name}/export",
    summary="Export a report as CSV, XLSX or PDF (binary response)",
    response_class=Response,
    responses={
        200: {
            "description": (
                "Binary file. Content-Type is text/csv, "
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet "
                "or application/pdf; the filename is in Content-Disposition."
            ),
            "content": {
                "text/csv": {},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
                "application/pdf": {},
            },
        }
    },
)
async def export_report(
    report_name: Literal[
        "sales-performance", "approval-status", "products", "discounts", "pipeline"
    ],
    user: InternalUser,
    db: DbSession,
    period: PeriodFilter,
    format: Annotated[ExportFormat, Query(description="csv | xlsx | pdf")] = "xlsx",
    group_by: Annotated[GroupBy, Query()] = "rep",
    rep_user_id: uuid.UUID | None = Query(default=None),
    team_id: uuid.UUID | None = Query(default=None),
    approval_status: ApprovalRequestStatus | None = Query(default=None),
    product_id: uuid.UUID | None = Query(default=None),
    category: ProductCategory | None = Query(default=None),
    customer_profile_id: uuid.UUID | None = Query(default=None),
) -> Response:
    """PDF A7.2 — "Export options: PDF / XLS"."""
    filters = await _filters(
        user,
        period,
        rep_user_id=rep_user_id,
        team_id=team_id,
        approval_status=approval_status,
        product_id=product_id,
        category=category,
        customer_profile_id=customer_profile_id,
    )

    if report_name == "sales-performance":
        payload = await ReportingService.sales_performance(
            db, filters, group_by=group_by
        )
    elif report_name == "approval-status":
        payload = await ReportingService.approval_status(db, filters)
    elif report_name == "products":
        payload = await ReportingService.products(db, filters)
    elif report_name == "discounts":
        payload = await ReportingService.discounts(db, filters)
    elif report_name == "pipeline":
        payload = await ReportingService.pipeline(db, filters)
    else:  # pragma: no cover - Literal already constrains this
        raise NotFoundError(f"Unknown report {report_name!r}.")

    headers, rows = ReportingService.flatten(report_name, payload)
    body, media_type, filename = ExportService.render(
        fmt=format,
        report_name=report_name,
        headers=headers,
        rows=rows,
        meta=payload.get("filters"),
    )
    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Exposed via CORS so a browser fetch can read the filename.
            "X-Export-Format": format,
            "X-Export-Rows": str(len(rows)),
        },
    )


@router.get(
    "/export/formats",
    summary="Supported export formats",
)
async def export_formats(user: InternalUser) -> dict[str, Any]:
    return {
        "formats": list(SUPPORTED_FORMATS),
        "default": "xlsx",
        "reports": [
            "sales-performance",
            "approval-status",
            "products",
            "discounts",
            "pipeline",
        ],
    }
