"""Quote, version and line schemas.

Two response shapes exist for every commercial object:

* ``*Read``       — internal. Includes cost, margin and risk.
* ``*PublicRead`` — customer portal. Cost/margin/risk fields do not exist on
  the model at all, so redaction cannot be forgotten at a call site.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, model_validator

from app.enums import (
    BillingType,
    PaymentTerms,
    ProductCategory,
    QuoteStatus,
    QuoteVersionSource,
    QuoteVersionStatus,
    RecurringInterval,
    RiskBand,
)
from app.schemas.common import ApiModel, ReadModel, TimestampedRead


# --------------------------------------------------------------------- lines
class QuoteLineCreate(ApiModel):
    product_id: uuid.UUID
    #: PDF A2 variants. The variant's ``price_delta`` and ``cost_delta`` are
    #: applied on top of the parent product's price and cost. Previously the
    #: column existed on the model with no way to set it, so variants could
    #: never reach a quote.
    product_variant_id: uuid.UUID | None = None
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    discount_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    #: Overrides the catalog price. Cost is never client-supplied.
    unit_list_price: Decimal | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=255)
    recurring_periods: int | None = Field(default=None, ge=1, le=120)
    notes: str | None = None


class QuoteLineUpdate(ApiModel):
    quantity: Decimal | None = Field(default=None, gt=0)
    discount_pct: Decimal | None = Field(default=None, ge=0, le=100)
    unit_list_price: Decimal | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=255)
    recurring_periods: int | None = Field(default=None, ge=1, le=120)
    notes: str | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "QuoteLineUpdate":
        if not self.model_dump(exclude_unset=True):
            raise ValueError("at least one field must be supplied")
        return self


class QuoteLineRead(TimestampedRead):
    quote_version_id: uuid.UUID
    product_id: uuid.UUID
    line_number: int
    description: str
    category: ProductCategory
    quantity: Decimal
    unit_list_price: Decimal
    unit_cost: Decimal
    unit_net_price: Decimal
    discount_pct: Decimal
    discount_amount: Decimal
    #: This line's share of the order-level discount.
    order_discount_amount: Decimal
    #: Line and order discounts compounded — the value policy ceilings judge.
    effective_discount_pct: Decimal
    gross_amount: Decimal
    net_amount: Decimal
    tax_rate_pct: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    line_cost: Decimal
    line_margin: Decimal
    line_margin_pct: Decimal
    billing_type: BillingType
    recurring_interval: RecurringInterval | None = None
    recurring_periods: int
    is_stock_tracked: bool
    product_variant_id: uuid.UUID | None = None
    notes: str | None = None


class QuoteLinePublicRead(ReadModel):
    """No ``unit_cost``, ``line_cost``, ``line_margin`` or ``line_margin_pct``."""

    id: uuid.UUID
    product_id: uuid.UUID
    line_number: int
    description: str
    category: ProductCategory
    quantity: Decimal
    unit_list_price: Decimal
    unit_net_price: Decimal
    discount_pct: Decimal
    discount_amount: Decimal
    #: The customer may see the total discount they received; what stays
    #: hidden is cost, margin and the internal risk reasoning.
    effective_discount_pct: Decimal
    gross_amount: Decimal
    net_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    billing_type: BillingType
    recurring_interval: RecurringInterval | None = None
    recurring_periods: int


# ------------------------------------------------------------------ versions
class QuoteVersionTotals(ReadModel):
    gross_revenue: Decimal
    total_discount: Decimal
    net_revenue: Decimal
    tax_amount: Decimal
    total_revenue: Decimal
    total_cost: Decimal
    margin: Decimal
    margin_pct: Decimal
    effective_discount_pct: Decimal
    one_time_revenue: Decimal
    recurring_revenue: Decimal


class QuoteVersionRead(TimestampedRead):
    quote_id: uuid.UUID
    version_number: int
    parent_version_id: uuid.UUID | None = None
    status: QuoteVersionStatus
    source: QuoteVersionSource
    revision_reason: str | None = None
    created_by_user_id: uuid.UUID
    currency: str
    payment_terms: PaymentTerms
    valid_until: date | None = None

    order_discount_pct: Decimal
    order_discount_amount: Decimal

    gross_revenue: Decimal
    total_discount: Decimal
    net_revenue: Decimal
    tax_amount: Decimal
    total_revenue: Decimal
    total_cost: Decimal
    margin: Decimal
    margin_pct: Decimal
    effective_discount_pct: Decimal
    one_time_revenue: Decimal
    recurring_revenue: Decimal

    blended_risk_score: Decimal
    risk_band: RiskBand
    requires_approval: bool
    is_stale: bool
    stale_reason: str | None = None

    calculated_at: datetime | None = None
    submitted_at: datetime | None = None
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    confirmed_at: datetime | None = None
    rejected_at: datetime | None = None
    superseded_at: datetime | None = None

    is_editable: bool
    lines: list[QuoteLineRead] = Field(default_factory=list)


class QuoteVersionPublicRead(ReadModel):
    """Customer-facing version. No cost, margin, or internal risk."""

    id: uuid.UUID
    quote_id: uuid.UUID
    version_number: int
    status: QuoteVersionStatus
    currency: str
    payment_terms: PaymentTerms
    valid_until: date | None = None

    gross_revenue: Decimal
    total_discount: Decimal
    net_revenue: Decimal
    tax_amount: Decimal
    total_revenue: Decimal
    effective_discount_pct: Decimal
    one_time_revenue: Decimal
    recurring_revenue: Decimal

    sent_at: datetime | None = None
    confirmed_at: datetime | None = None
    lines: list[QuoteLinePublicRead] = Field(default_factory=list)


# -------------------------------------------------------------------- quotes
class QuoteCreate(ApiModel):
    title: str = Field(min_length=1, max_length=255)
    payment_terms: PaymentTerms | None = None
    valid_until: date | None = None
    #: PDF B3 — an order-level discount applied on top of any line discounts.
    order_discount_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    #: Optional convenience: create V1 with these lines in one call.
    lines: list[QuoteLineCreate] = Field(default_factory=list)


class QuoteVersionSummary(ReadModel):
    id: uuid.UUID
    version_number: int
    status: QuoteVersionStatus
    source: QuoteVersionSource
    total_revenue: Decimal
    margin_pct: Decimal
    blended_risk_score: Decimal
    is_stale: bool
    created_at: datetime


class QuoteRead(TimestampedRead):
    quote_number: str
    title: str
    deal_id: uuid.UUID
    status: QuoteStatus
    current_version_number: int
    current_version_id: uuid.UUID | None = None
    versions: list[QuoteVersionSummary] = Field(default_factory=list)


class QuotePublicSummary(ReadModel):
    """Portal list item."""

    quote_id: uuid.UUID
    quote_number: str
    title: str
    current_version_id: uuid.UUID
    version_number: int
    status: QuoteVersionStatus
    total_revenue: Decimal
    currency: str
    valid_until: date | None = None
    awaiting_customer: bool
    can_confirm: bool
    blocked_reason: str | None = None


class QuotePublicRead(ReadModel):
    quote_id: uuid.UUID
    quote_number: str
    title: str
    seller_name: str
    status: QuoteStatus
    current_version: QuoteVersionPublicRead
    can_confirm: bool
    blocked_reason: str | None = None


class QuoteListItem(ReadModel):
    """Flat list row for the Quotations screen and Kanban pipeline (PDF B1/B2).

    Carries everything B2's cards need — "customer, amount, and stage" — in one
    payload, so the list does not require a request per quote.
    """

    quote_id: uuid.UUID
    quote_number: str
    title: str
    status: QuoteStatus

    deal_id: uuid.UUID
    deal_reference: str
    deal_stage: str

    customer_profile_id: uuid.UUID
    customer_display_name: str | None = None
    customer_tier: str | None = None

    current_version_id: uuid.UUID | None = None
    current_version_number: int
    current_version_status: QuoteVersionStatus | None = None

    total_revenue: Decimal
    net_revenue: Decimal
    margin_pct: Decimal
    effective_discount_pct: Decimal
    blended_risk_score: Decimal
    risk_band: RiskBand | None = None
    requires_approval: bool
    is_stale: bool

    owner_user_id: uuid.UUID
    owner_name: str | None = None
    line_count: int
    version_count: int
    #: Days since the quote was created — drives the stalled-deal styling.
    age_days: int
    last_activity_at: datetime
    created_at: datetime


class RevisionCreate(ApiModel):
    reason: str = Field(min_length=1, max_length=2000)
    #: Line changes to apply to the new version, keyed by existing line id.
    line_updates: dict[uuid.UUID, QuoteLineUpdate] = Field(default_factory=dict)
    add_lines: list[QuoteLineCreate] = Field(default_factory=list)
    remove_line_ids: list[uuid.UUID] = Field(default_factory=list)
    payment_terms: PaymentTerms | None = None
    order_discount_pct: Decimal | None = Field(default=None, ge=0, le=100)


class OrderDiscountUpdate(ApiModel):
    """PDF B3 — order-level discount, applied on top of the line discounts."""

    order_discount_pct: Decimal = Field(ge=0, le=100)


class QuoteLoseRequest(ApiModel):
    reason: str = Field(min_length=1, max_length=2000)


class SubmitRequest(ApiModel):
    note: str | None = Field(default=None, max_length=2000)


class SendRequest(ApiModel):
    note: str | None = Field(default=None, max_length=2000)
