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
    #: PDF B9 nudge / escalation state.
    acknowledged_at: datetime | None = None
    acknowledged_by_user_id: uuid.UUID | None = None
    nudge_count: int = 0
    last_nudged_at: datetime | None = None
    escalated_at: datetime | None = None
    escalation_note: str | None = None


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


class AttentionItemAcknowledge(ApiModel):
    """PDF B9 — "I have seen this and I am on it", short of resolving it."""

    note: str | None = Field(default=None, max_length=1000)


class AttentionItemNudge(ApiModel):
    """PDF B9 — "An automated nudge ... can be triggered from an alert"."""

    note: str | None = Field(default=None, max_length=1000)


class AttentionItemEscalate(ApiModel):
    """PDF B9 — escalation raises severity and may reassign the owner."""

    note: str = Field(min_length=1, max_length=1000)
    #: Omit to leave ownership unchanged and only raise severity.
    owner_role: RoleCode | None = None


class NudgeResponse(ReadModel):
    item: AttentionItemRead
    message: str
    notified_role: RoleCode
    nudge_count: int
