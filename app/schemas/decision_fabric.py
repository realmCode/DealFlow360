"""Decision Fabric result schemas — the central explainability contract."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.enums import ApprovalLevel, Severity
from app.schemas.common import ReadModel
from app.schemas.policy import PolicyResultRead


class FieldChange(ReadModel):
    field: str
    subject: str | None = None
    quote_line_id: uuid.UUID | None = None
    old_value: Any | None = None
    new_value: Any | None = None
    material: bool


class MaterialChange(ReadModel):
    field: str
    subject: str | None = None
    quote_line_id: uuid.UUID | None = None
    old: Any | None = None
    new: Any | None = None
    severity: Severity
    reason: str


class StaleDecision(ReadModel):
    approval_request_id: uuid.UUID
    previous_decision: str
    reason: str
    decided_at: datetime | None = None
    decided_by: str | None = None


class AffectedEntity(ReadModel):
    type: str
    id: uuid.UUID
    reason: str


class RequiredApproval(ReadModel):
    type: ApprovalLevel
    reason: str
    triggered_by: list[str] = Field(default_factory=list)


class AttentionItemDraft(ReadModel):
    type: str
    severity: Severity
    title: str
    reason: str
    impact: str
    owner_role: str
    recommended_action: str


class DecisionExplanation(ReadModel):
    """Human-readable narrative. Every field is prose, not a code."""

    summary: str
    causal_chain: list[str] = Field(default_factory=list)
    what_changed: str
    why_it_matters: str
    who_is_affected: str
    what_happens_next: str


class DecisionFabricResult(ReadModel):
    quote_id: uuid.UUID
    quote_version_id: uuid.UUID
    previous_version_id: uuid.UUID | None = None
    evaluated_at: datetime

    changes: list[FieldChange] = Field(default_factory=list)
    material_changes: list[MaterialChange] = Field(default_factory=list)
    policy_results: list[PolicyResultRead] = Field(default_factory=list)
    stale_decisions: list[StaleDecision] = Field(default_factory=list)
    affected_entities: list[AffectedEntity] = Field(default_factory=list)
    required_approvals: list[RequiredApproval] = Field(default_factory=list)
    attention_items: list[AttentionItemDraft] = Field(default_factory=list)
    explanation: DecisionExplanation

    #: Convenience flags for the frontend.
    has_material_change: bool = False
    blocks_confirmation: bool = False
