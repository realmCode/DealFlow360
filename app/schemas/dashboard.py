"""Control Tower / dashboard schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from app.enums import (
    AttentionItemStatus,
    AttentionItemType,
    DealStage,
    RoleCode,
    Severity,
)
from app.schemas.common import ApiModel, ReadModel


class AttentionItemRead(ReadModel):
    id: uuid.UUID
    source_type: str
    source_id: uuid.UUID
    type: AttentionItemType
    severity: Severity
    title: str
    reason: str
    impact: str
    owner_role: RoleCode
    owner_user_id: uuid.UUID | None = None
    recommended_action: str
    status: AttentionItemStatus
    deal_id: uuid.UUID | None = None
    quote_id: uuid.UUID | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    resolved_at: datetime | None = None


class AttentionItemGroup(ReadModel):
    severity: Severity
    count: int
    items: list[AttentionItemRead]


class ControlTowerCounts(ReadModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    total_open: int = 0


class ControlTowerRead(ReadModel):
    """An action queue, not a KPI wall."""

    organization_id: uuid.UUID
    generated_at: datetime
    counts: ControlTowerCounts
    by_type: dict[str, int] = Field(default_factory=dict)
    groups: list[AttentionItemGroup] = Field(default_factory=list)
    my_queue: list[AttentionItemRead] = Field(default_factory=list)
    headline: str


class DealHealthSignal(ReadModel):
    code: str
    label: str
    severity: Severity
    detail: str
    points: int


class DealHealthRead(ReadModel):
    deal_id: uuid.UUID
    deal_reference: str
    deal_name: str
    customer_name: str
    stage: DealStage
    health_score: int = Field(ge=0, le=100)
    health_band: str
    total_value: Decimal
    margin_pct: Decimal
    blocked: bool
    signals: list[DealHealthSignal] = Field(default_factory=list)
    open_attention_items: int
    summary: str


class DealHealthList(ReadModel):
    generated_at: datetime
    average_health: int
    deals: list[DealHealthRead]


class AuditEventRead(ReadModel):
    id: uuid.UUID
    sequence: int
    event_type: str
    entity_type: str
    entity_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    actor_email: str | None = None
    actor_role: RoleCode | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class AttentionItemResolve(ApiModel):
    resolution_note: str | None = Field(default=None, max_length=1000)
