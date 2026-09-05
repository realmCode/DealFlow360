"""Sales order and fulfillment schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.enums import (
    BillingType,
    FulfillmentStatus,
    PaymentTerms,
    ProductCategory,
    RecurringInterval,
    SalesOrderStatus,
)
from app.schemas.common import ReadModel, TimestampedRead


class SalesOrderLineRead(ReadModel):
    id: uuid.UUID
    line_number: int
    product_id: uuid.UUID
    quote_line_id: uuid.UUID
    description: str
    category: ProductCategory
    quantity: Decimal
    unit_list_price: Decimal
    unit_net_price: Decimal
    unit_cost: Decimal
    discount_pct: Decimal
    discount_amount: Decimal
    net_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    line_cost: Decimal
    billing_type: BillingType
    recurring_interval: RecurringInterval | None = None
    recurring_periods: int
    is_stock_tracked: bool
    quantity_allocated: Decimal
    quantity_backordered: Decimal
    quantity_fulfilled: Decimal


class AllocationRead(ReadModel):
    id: uuid.UUID
    sales_order_line_id: uuid.UUID
    product_id: uuid.UUID
    warehouse_id: uuid.UUID | None = None
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    quantity: Decimal
    status: str
    mode: str
    expected_available_at: datetime | None = None
    notes: str | None = None


class FulfillmentRead(ReadModel):
    id: uuid.UUID
    fulfillment_number: str
    warehouse_id: uuid.UUID
    warehouse_name: str | None = None
    shipment_sequence: int
    status: FulfillmentStatus
    carrier: str | None = None
    tracking_number: str | None = None
    shipping_cost: Decimal
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None


class SalesOrderRead(TimestampedRead):
    order_number: str
    deal_id: uuid.UUID
    quote_id: uuid.UUID
    quote_version_id: uuid.UUID
    customer_profile_id: uuid.UUID
    customer_organization_id: uuid.UUID
    customer_name: str | None = None
    status: SalesOrderStatus
    currency: str
    payment_terms: PaymentTerms

    gross_revenue: Decimal
    total_discount: Decimal
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    total_cost: Decimal
    margin: Decimal
    margin_pct: Decimal
    one_time_amount: Decimal
    recurring_amount: Decimal

    confirmed_by_user_id: uuid.UUID
    confirmed_at: datetime
    fully_allocated: bool
    has_backorder: bool
    allocated_at: datetime | None = None
    fulfilled_at: datetime | None = None

    lines: list[SalesOrderLineRead] = Field(default_factory=list)
    allocations: list[AllocationRead] = Field(default_factory=list)
    fulfillments: list[FulfillmentRead] = Field(default_factory=list)


class OrderPublicRead(ReadModel):
    """Portal confirmation receipt — no cost or margin."""

    id: uuid.UUID
    order_number: str
    status: SalesOrderStatus
    currency: str
    payment_terms: PaymentTerms
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    one_time_amount: Decimal
    recurring_amount: Decimal
    confirmed_at: datetime


class ConfirmResponse(ReadModel):
    order: OrderPublicRead
    message: str
    idempotent_replay: bool = False
