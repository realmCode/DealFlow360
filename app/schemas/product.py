"""Product, variant and price-list schemas."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import Field, model_validator

from app.enums import BillingType, CustomerTier, ProductCategory, RecurringInterval
from app.schemas.common import ApiModel, ReadModel, TimestampedRead


class ProductCreate(ApiModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category: ProductCategory
    list_price: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    internal_cost: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    tax_rate_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    uom: str = Field(default="EACH", max_length=32)
    billing_type: BillingType = BillingType.ONE_TIME
    recurring_interval: RecurringInterval | None = None
    default_recurring_periods: int = Field(default=1, ge=1, le=120)
    is_stock_tracked: bool = False

    @model_validator(mode="after")
    def _check_recurring(self) -> "ProductCreate":
        if self.billing_type is BillingType.RECURRING and self.recurring_interval is None:
            raise ValueError("recurring products require a recurring_interval")
        if self.billing_type is BillingType.ONE_TIME and self.recurring_interval is not None:
            raise ValueError("one-time products must not set a recurring_interval")
        return self


class ProductUpdate(ApiModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    list_price: Decimal | None = Field(default=None, ge=0)
    internal_cost: Decimal | None = Field(default=None, ge=0)
    tax_rate_pct: Decimal | None = Field(default=None, ge=0, le=100)
    is_active: bool | None = None
    #: PDF A6.2 — promoted products rank higher in upsell suggestions and
    #: carry a promotion tag in the panel.
    is_promoted: bool | None = None


class ProductRead(TimestampedRead):
    """Internal view — includes ``internal_cost``. Never returned to portal users."""

    sku: str
    name: str
    description: str | None = None
    category: ProductCategory
    list_price: Decimal
    internal_cost: Decimal
    tax_rate_pct: Decimal
    uom: str
    billing_type: BillingType
    recurring_interval: RecurringInterval | None = None
    default_recurring_periods: int
    is_stock_tracked: bool
    is_active: bool
    is_promoted: bool = False
    #: Convenience for the builder: unit_margin is list_price - internal_cost.
    unit_margin: Decimal | None = None


class ProductPublicRead(ReadModel):
    """Customer-facing view. ``internal_cost`` is structurally absent."""

    id: uuid.UUID
    sku: str
    name: str
    description: str | None = None
    category: ProductCategory
    list_price: Decimal
    uom: str
    billing_type: BillingType
    recurring_interval: RecurringInterval | None = None


class ProductVariantCreate(ApiModel):
    product_id: uuid.UUID
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    attributes: dict[str, Any] = Field(default_factory=dict)
    price_delta: Decimal = Field(default=Decimal("0"))
    cost_delta: Decimal = Field(default=Decimal("0"))


class ProductVariantUpdate(ApiModel):
    name: str | None = Field(default=None, max_length=255)
    attributes: dict[str, Any] | None = None
    price_delta: Decimal | None = None
    cost_delta: Decimal | None = None
    is_active: bool | None = None


class ProductVariantRead(TimestampedRead):
    product_id: uuid.UUID
    sku: str
    name: str
    attributes: dict[str, Any]
    price_delta: Decimal
    cost_delta: Decimal
    is_active: bool


class PriceListCreate(ApiModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    tier: CustomerTier | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    rules: list[dict[str, Any]] = Field(default_factory=list)
    valid_from: date | None = None
    valid_to: date | None = None


class PriceListUpdate(ApiModel):
    name: str | None = Field(default=None, max_length=255)
    tier: CustomerTier | None = None
    #: Replaces the whole rule set. Each entry is
    #: ``{"product_id": "<uuid>", "unit_price": "1100.00"}``.
    rules: list[dict[str, Any]] | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    is_active: bool | None = None


class PriceListRead(TimestampedRead):
    code: str
    name: str
    tier: CustomerTier | None = None
    currency: str
    rules: list[Any]
    valid_from: date | None = None
    valid_to: date | None = None
    is_active: bool
