"""Warehouse, inventory and allocation schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.schemas.common import ApiModel, ReadModel, TimestampedRead


class WarehouseCreate(ApiModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    region: str | None = Field(default=None, max_length=128)
    address_line1: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=128)
    country: str | None = Field(default=None, max_length=64)
    postal_code: str | None = Field(default=None, max_length=64)
    priority: int = Field(default=100, ge=0, le=10_000)
    shipping_cost_per_shipment: Decimal = Field(default=Decimal("0"), ge=0)


class WarehouseRead(TimestampedRead):
    code: str
    name: str
    region: str | None = None
    city: str | None = None
    country: str | None = None
    priority: int
    shipping_cost_per_shipment: Decimal
    is_active: bool


class InventoryUpsert(ApiModel):
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    quantity_on_hand: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    quantity_inbound: Decimal = Field(default=Decimal("0"), ge=0)
    reorder_point: Decimal = Field(default=Decimal("0"), ge=0)
    expected_restock_at: datetime | None = None


class InventoryAdjust(ApiModel):
    """Positive delta = stock arriving (restock), negative = shrinkage."""

    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    quantity_delta: Decimal = Field(max_digits=18, decimal_places=4)
    reason: str = Field(min_length=1, max_length=500)


class InventoryRead(TimestampedRead):
    warehouse_id: uuid.UUID
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    product_id: uuid.UUID
    product_sku: str | None = None
    product_name: str | None = None
    quantity_on_hand: Decimal
    quantity_reserved: Decimal
    quantity_available: Decimal
    quantity_inbound: Decimal
    reorder_point: Decimal
    expected_restock_at: datetime | None = None


class ManualAllocationLine(ApiModel):
    sales_order_line_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)


class AllocateRequest(ApiModel):
    """Empty body = automatic allocation. Supply ``overrides`` to place stock
    manually; overrides are still validated against real availability."""

    overrides: list[ManualAllocationLine] = Field(default_factory=list)
    allow_partial: bool = Field(
        default=True,
        description="When false, the whole allocation fails if any line is short.",
    )


class AllocationPlanLine(ReadModel):
    sales_order_line_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    quantity_requested: Decimal
    quantity_allocated: Decimal
    quantity_backordered: Decimal
    splits: list[dict[str, str]] = Field(default_factory=list)
    explanation: str


class AllocationResult(ReadModel):
    sales_order_id: uuid.UUID
    status: str
    fully_allocated: bool
    has_backorder: bool
    shipment_count: int
    estimated_shipping_cost: Decimal
    lines: list[AllocationPlanLine] = Field(default_factory=list)
    idempotent_replay: bool = False
    message: str


class FulfillRequest(ApiModel):
    warehouse_id: uuid.UUID | None = Field(
        default=None,
        description="Ship only this warehouse's allocations. Omit to ship all.",
    )
    carrier: str | None = Field(default=None, max_length=128)
    tracking_number: str | None = Field(default=None, max_length=128)
