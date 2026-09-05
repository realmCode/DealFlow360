"""Approval workflow schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from app.enums import (
    ApprovalDecisionType,
    ApprovalLevel,
    ApprovalRequestStatus,
    ApprovalStepStatus,
    RoleCode,
)
from app.schemas.common import ApiModel, ReadModel, TimestampedRead


class ApprovalStepRead(ReadModel):
    id: uuid.UUID
    sequence: int
    level: ApprovalLevel
    required_role: RoleCode
    status: ApprovalStepStatus
    reason: str
    assigned_user_id: uuid.UUID | None = None
    decided_by_user_id: uuid.UUID | None = None
    decided_by_email: str | None = None
    decision_reason: str | None = None
    decided_at: datetime | None = None


class ApprovalDecisionRead(ReadModel):
    id: uuid.UUID
    approval_step_id: uuid.UUID
    decision: ApprovalDecisionType
    actor_user_id: uuid.UUID
    actor_role: RoleCode
    actor_email: str
    reason: str
    decided_at: datetime
    decision_snapshot: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequestRead(TimestampedRead):
    quote_id: uuid.UUID
    quote_version_id: uuid.UUID
    quote_number: str | None = None
    version_number: int | None = None
    customer_name: str | None = None
    status: ApprovalRequestStatus
    requested_by_user_id: uuid.UUID
    requested_by_email: str | None = None
    reason: str
    required_levels: list[Any] = Field(default_factory=list)
    policy_summary: dict[str, Any] = Field(default_factory=dict)
    blended_risk_score: Decimal
    current_step_sequence: int
    decided_at: datetime | None = None
    stale_at: datetime | None = None
    stale_reason: str | None = None
    steps: list[ApprovalStepRead] = Field(default_factory=list)
    decisions: list[ApprovalDecisionRead] = Field(default_factory=list)
    #: Populated on detail reads so an approver sees the numbers they sign off.
    financials: dict[str, Any] | None = None


class ApprovalInboxItem(ReadModel):
    approval_request_id: uuid.UUID
    approval_step_id: uuid.UUID
    quote_id: uuid.UUID
    quote_version_id: uuid.UUID
    quote_number: str
    version_number: int
    title: str
    customer_name: str
    level: ApprovalLevel
    sequence: int
    reason: str
    blended_risk_score: Decimal
    total_revenue: Decimal
    margin_pct: Decimal
    requested_by_email: str
    is_reapproval: bool
    waiting_since: datetime


class ApprovalActionRequest(ApiModel):
    reason: str = Field(min_length=1, max_length=2000)


class ApprovalActionResponse(ReadModel):
    approval_request: ApprovalRequestRead
    quote_version_status: str
    message: str
