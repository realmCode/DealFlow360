"""What-if simulation schemas.

Turns the blended risk score from a verdict delivered after submission into a
planning tool the rep can consult before it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field, model_validator

from app.enums import PaymentTerms, RiskBand
from app.schemas.common import ApiModel, ReadModel


class SimulationRequest(ApiModel):
    """Hypothetical changes. Nothing here is persisted."""

    #: New discount percentage per existing line id.
    line_discounts: dict[uuid.UUID, Decimal] = Field(default_factory=dict)
    #: New quantity per existing line id.
    line_quantities: dict[uuid.UUID, Decimal] = Field(default_factory=dict)
    order_discount_pct: Decimal | None = Field(default=None, ge=0, le=100)
    payment_terms: PaymentTerms | None = None

    @model_validator(mode="after")
    def _needs_a_hypothesis(self) -> "SimulationRequest":
        if (
            not self.line_discounts
            and not self.line_quantities
            and self.order_discount_pct is None
            and self.payment_terms is None
        ):
            raise ValueError(
                "supply at least one of line_discounts, line_quantities, "
                "order_discount_pct or payment_terms"
            )
        for value in self.line_discounts.values():
            if value < 0 or value > 100:
                raise ValueError("line discounts must be between 0 and 100")
        for value in self.line_quantities.values():
            if value <= 0:
                raise ValueError("line quantities must be greater than zero")
        return self


class SimulatedLine(ReadModel):
    quote_line_id: uuid.UUID
    description: str
    category: str
    quantity: Decimal
    discount_pct: Decimal
    effective_discount_pct: Decimal
    net_amount: Decimal
    line_margin: Decimal
    line_margin_pct: Decimal


class SimulationScenario(ReadModel):
    """One scored scenario — either the current state or the hypothesis."""

    gross_revenue: Decimal
    total_discount: Decimal
    order_discount_pct: Decimal
    order_discount_amount: Decimal
    net_revenue: Decimal
    tax_amount: Decimal
    total_revenue: Decimal
    total_cost: Decimal
    margin: Decimal
    margin_pct: Decimal
    effective_discount_pct: Decimal
    blended_risk_score: Decimal
    risk_band: RiskBand
    #: Per-component arithmetic, so the score is explainable in the UI.
    risk_components: list[dict[str, Any]] = Field(default_factory=list)
    risk_explanation: str
    requires_approval: bool
    required_approvals: list[str] = Field(default_factory=list)
    violation_count: int
    violations: list[str] = Field(default_factory=list)
    payment_terms: PaymentTerms
    lines: list[SimulatedLine] = Field(default_factory=list)


class SimulationResult(ReadModel):
    quote_version_id: uuid.UUID
    simulated_at: datetime
    baseline: SimulationScenario
    proposed: SimulationScenario

    margin_delta: Decimal
    margin_pct_delta: Decimal
    revenue_delta: Decimal
    risk_delta: Decimal
    #: Approval levels the change would newly require.
    approvals_added: list[str] = Field(default_factory=list)
    #: Approval levels the change would remove.
    approvals_removed: list[str] = Field(default_factory=list)
    #: One sentence a rep can act on without reading the numbers.
    verdict: str
    #: Always false. Present so the contract states it explicitly.
    persisted: bool = False
