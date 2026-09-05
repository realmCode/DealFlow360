"""Policy and policy-result schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from app.enums import (
    ApprovalLevel,
    CustomerTier,
    PolicyComparison,
    PolicyResultStatus,
    PolicyType,
    PolicyUnit,
    ProductCategory,
    RiskBand,
    Severity,
)
from app.schemas.common import ApiModel, ReadModel, TimestampedRead


class PolicyCreate(ApiModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    policy_type: PolicyType
    customer_tier: CustomerTier | None = None
    product_category: ProductCategory | None = None
    customer_profile_id: uuid.UUID | None = None
    threshold_value: Decimal = Field(max_digits=18, decimal_places=4)
    comparison: PolicyComparison = PolicyComparison.LTE
    unit: PolicyUnit = PolicyUnit.PERCENT
    required_action: ApprovalLevel = ApprovalLevel.SALES_MANAGER
    severity: Severity = Severity.MEDIUM
    priority: int = Field(default=100, ge=0, le=10_000)
    effective_from: date | None = None
    effective_to: date | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class PolicyUpdate(ApiModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    threshold_value: Decimal | None = None
    required_action: ApprovalLevel | None = None
    severity: Severity | None = None
    priority: int | None = Field(default=None, ge=0, le=10_000)
    is_active: bool | None = None


class PolicyRead(TimestampedRead):
    code: str
    name: str
    description: str | None = None
    policy_type: PolicyType
    customer_tier: CustomerTier | None = None
    product_category: ProductCategory | None = None
    customer_profile_id: uuid.UUID | None = None
    threshold_value: Decimal
    comparison: PolicyComparison
    unit: PolicyUnit
    required_action: ApprovalLevel
    severity: Severity
    priority: int
    is_active: bool
    effective_from: date | None = None
    effective_to: date | None = None
    config: dict[str, Any]


class PolicyResultRead(ReadModel):
    """Always explainable: a number is never returned without its reason."""

    id: uuid.UUID
    quote_version_id: uuid.UUID
    policy_id: uuid.UUID | None = None
    quote_line_id: uuid.UUID | None = None
    rule: str
    status: PolicyResultStatus
    subject: str | None = None
    actual_value: Decimal
    threshold_value: Decimal
    overage_points: Decimal
    unit: PolicyUnit
    scope_category: ProductCategory | None = None
    scope_tier: CustomerTier | None = None
    reason: str
    required_action: ApprovalLevel | None = None
    severity: Severity
    risk_contribution: Decimal
    detail: dict[str, Any]
    evaluated_at: datetime


class RiskComponent(ReadModel):
    """One additive term of the blended risk score, with its arithmetic."""

    name: str
    raw_value: Decimal
    weight: Decimal
    points: Decimal
    cap: Decimal
    explanation: str


class BlendedRiskRead(ReadModel):
    score: Decimal
    band: RiskBand
    tier: CustomerTier
    tier_sensitivity: Decimal
    components: list[RiskComponent]
    formula: str
    explanation: str


class PolicyEvaluationRead(ReadModel):
    quote_version_id: uuid.UUID
    evaluated_at: datetime
    policy_results: list[PolicyResultRead]
    blended_risk: BlendedRiskRead
    required_approvals: list[dict[str, Any]]
    requires_approval: bool
    violation_count: int
