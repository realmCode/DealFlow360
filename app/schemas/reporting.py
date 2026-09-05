"""Reporting, settings and sales-team schemas — PDF module A7."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from app.schemas.common import ApiModel, ReadModel, TimestampedRead


# ------------------------------------------------------------------ reports
class ReportRowRead(ReadModel):
    """One grouped row. Money and percentages are strings, as everywhere."""

    group_key: str
    group_label: str
    quote_count: int
    version_count: int
    gross_revenue: Decimal
    total_discount: Decimal
    net_revenue: Decimal
    total_cost: Decimal
    margin: Decimal
    margin_pct: Decimal
    avg_discount_pct: Decimal
    avg_blended_risk: Decimal
    won_count: int
    lost_count: int
    win_rate_pct: Decimal


class ReportTotals(ReadModel):
    quote_count: int
    gross_revenue: Decimal
    total_discount: Decimal
    net_revenue: Decimal
    total_cost: Decimal
    margin: Decimal
    margin_pct: Decimal
    effective_discount_pct: Decimal
    won_count: int
    lost_count: int
    win_rate_pct: Decimal


class SalesPerformanceReport(ReadModel):
    group_by: str
    #: Echo of the applied filters, so an exported file is self-describing.
    filters: dict[str, Any]
    rows: list[ReportRowRead]
    totals: ReportTotals


class ApprovalStatusReport(ReadModel):
    filters: dict[str, Any]
    #: Keyed by ApprovalRequestStatus. Every state is present, including zeros.
    by_status: dict[str, dict[str, Any]]
    total_requests: int


class ProductReportEntry(ReadModel):
    product_id: uuid.UUID
    sku: str
    name: str
    category: str
    units_sold: Decimal
    order_count: int
    net_revenue: Decimal
    total_cost: Decimal
    margin: Decimal
    margin_pct: Decimal
    total_discount_given: Decimal
    avg_discount_pct: Decimal


class ProductReport(ReadModel):
    filters: dict[str, Any]
    best_selling: list[ProductReportEntry]
    most_discounted: list[ProductReportEntry]
    highest_margin_contribution: list[ProductReportEntry]
    product_count: int


class DiscountByRep(ReadModel):
    rep_user_id: uuid.UUID | None = None
    rep_name: str
    version_count: int
    avg_discount_pct: Decimal
    min_discount_pct: Decimal
    max_discount_pct: Decimal
    stdev_discount_pct: Decimal
    total_discount_given: Decimal
    avg_margin_pct: Decimal
    required_approval_count: int


class DiscountBand(ReadModel):
    band: str
    count: int


class DiscountReport(ReadModel):
    filters: dict[str, Any]
    by_rep: list[DiscountByRep]
    distribution: list[DiscountBand]


class PipelineReport(ReadModel):
    filters: dict[str, Any]
    #: Keyed by DealStage. Every stage present, including zeros.
    by_stage: dict[str, dict[str, Any]]
    total_deals: int
    won_count: int
    lost_count: int
    win_rate_pct: Decimal


# ------------------------------------------------------- discount anomalies
class DiscountBaselineRead(ReadModel):
    user_id: uuid.UUID
    sample_count: int
    mean_discount_pct: Decimal
    stdev: Decimal
    min_discount_pct: Decimal
    max_discount_pct: Decimal
    is_reliable: bool
    min_samples_required: int


class DiscountAnomalyRead(ReadModel):
    """PDF B9.2. Carries the arithmetic so the alert is defensible."""

    quote_id: uuid.UUID
    quote_version_id: uuid.UUID
    quote_number: str
    version_number: int
    customer_name: str | None = None
    rep_user_id: uuid.UUID
    rep_name: str | None = None
    is_anomaly: bool
    effective_discount_pct: Decimal
    sigma_threshold: Decimal
    deviations_above_mean: Decimal
    trigger_at_pct: Decimal
    severity: str
    reason: str
    baseline: DiscountBaselineRead
    created_at: datetime


class DiscountAnomalyList(ReadModel):
    generated_at: datetime
    anomaly_count: int
    items: list[DiscountAnomalyRead]


# ----------------------------------------------------------------- settings
class OrganizationSettingsRead(TimestampedRead):
    organization_id: uuid.UUID
    finance_escalation_threshold: Decimal
    risk_discount_overage_weight: Decimal
    risk_breadth_weight: Decimal
    risk_margin_weight: Decimal
    risk_depth_weight: Decimal
    stalled_deal_days: int
    discount_anomaly_sigma: Decimal
    discount_anomaly_min_samples: int
    approval_sla_hours: int
    recommendation_min_margin_pct: Decimal


class OrganizationSettingsUpdate(ApiModel):
    """PDF A3 — the approval chain and thresholds must be configurable."""

    finance_escalation_threshold: Decimal | None = Field(
        default=None, ge=0, le=100
    )
    risk_discount_overage_weight: Decimal | None = Field(default=None, ge=0, le=100)
    risk_breadth_weight: Decimal | None = Field(default=None, ge=0, le=100)
    risk_margin_weight: Decimal | None = Field(default=None, ge=0, le=100)
    risk_depth_weight: Decimal | None = Field(default=None, ge=0, le=100)
    stalled_deal_days: int | None = Field(default=None, ge=1, le=365)
    discount_anomaly_sigma: Decimal | None = Field(default=None, gt=0, le=10)
    discount_anomaly_min_samples: int | None = Field(default=None, ge=2, le=1000)
    approval_sla_hours: int | None = Field(default=None, ge=1, le=8760)
    recommendation_min_margin_pct: Decimal | None = Field(
        default=None, ge=0, le=100
    )


# -------------------------------------------------------------- sales teams
class SalesTeamCreate(ApiModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    manager_user_id: uuid.UUID | None = None
    region: str | None = Field(default=None, max_length=128)
    #: Convenience: seed membership at creation time.
    member_user_ids: list[uuid.UUID] = Field(default_factory=list)


class SalesTeamUpdate(ApiModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    manager_user_id: uuid.UUID | None = None
    region: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None


class SalesTeamMemberRead(ReadModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str


class SalesTeamRead(TimestampedRead):
    code: str
    name: str
    description: str | None = None
    manager_user_id: uuid.UUID | None = None
    manager_name: str | None = None
    region: str | None = None
    is_active: bool
    members: list[SalesTeamMemberRead] = Field(default_factory=list)


class SalesTeamMemberAdd(ApiModel):
    user_ids: list[uuid.UUID] = Field(min_length=1)
