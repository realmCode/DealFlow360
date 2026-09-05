"""Tables 6-8/33 — products, product_variants, price_lists."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import (
    BillingType,
    CustomerTier,
    ProductCategory,
    RecurringInterval,
    enum_col,
)
from app.models.base import (
    Base,
    JsonDict,
    LongText,
    OrgOwnedMixin,
    Percent,
    Str32,
    Str64,
    Str255,
    TimestampMixin,
    UnitMoney,
    UUIDPrimaryKeyMixin,
)


class Product(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """Catalog item. ``internal_cost`` is employee-only data."""

    __tablename__ = "products"
    __table_args__ = (
        sa.UniqueConstraint("organization_id", "sku", name="uq_products_organization_id_sku"),
        sa.CheckConstraint("list_price >= 0", name="list_price_non_negative"),
        sa.CheckConstraint("internal_cost >= 0", name="internal_cost_non_negative"),
        sa.Index("ix_products_organization_id_category", "organization_id", "category"),
    )

    sku: Mapped[Str64] = mapped_column(nullable=False)
    name: Mapped[Str255] = mapped_column(nullable=False)
    description: Mapped[LongText | None] = mapped_column(nullable=True)
    category: Mapped[ProductCategory] = mapped_column(
        enum_col(ProductCategory), nullable=False
    )
    list_price: Mapped[UnitMoney] = mapped_column(nullable=False)
    internal_cost: Mapped[UnitMoney] = mapped_column(nullable=False)
    tax_rate_pct: Mapped[Percent] = mapped_column(
        nullable=False, default=Decimal("0.0000")
    )
    uom: Mapped[Str32] = mapped_column(nullable=False, default="EACH")

    billing_type: Mapped[BillingType] = mapped_column(
        enum_col(BillingType), nullable=False, default=BillingType.ONE_TIME
    )
    recurring_interval: Mapped[RecurringInterval | None] = mapped_column(
        enum_col(RecurringInterval), nullable=True
    )
    #: Default number of billed periods for recurring products (e.g. 12 monthly).
    default_recurring_periods: Mapped[int] = mapped_column(nullable=False, default=1)

    #: Physical goods draw down warehouse inventory; services do not.
    is_stock_tracked: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    #: PDF A6.2 — "Mark products as currently promoted so they rank higher in
    #: suggestions", which is also what lets B5 render a promotion tag.
    is_promoted: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=sa.false()
    )

    @property
    def unit_margin(self) -> Decimal:
        return self.list_price - self.internal_cost


class ProductVariant(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """P1 — size/pack options expressed as deltas on the parent product."""

    __tablename__ = "product_variants"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id", "sku", name="uq_product_variants_organization_id_sku"
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sku: Mapped[Str64] = mapped_column(nullable=False)
    name: Mapped[Str255] = mapped_column(nullable=False)
    attributes: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)
    price_delta: Mapped[UnitMoney] = mapped_column(
        nullable=False, default=Decimal("0.0000")
    )
    cost_delta: Mapped[UnitMoney] = mapped_column(
        nullable=False, default=Decimal("0.0000")
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    product: Mapped[Product] = relationship(lazy="selectin")


class PriceList(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """P1 — tier-based pricing rules.

    ``rules`` holds ``[{"product_id": ..., "unit_price": "1100.00"}, ...]`` so
    new rule shapes do not require a migration during the hackathon.
    """

    __tablename__ = "price_lists"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id", "code", name="uq_price_lists_organization_id_code"
        ),
    )

    code: Mapped[Str64] = mapped_column(nullable=False)
    name: Mapped[Str255] = mapped_column(nullable=False)
    tier: Mapped[CustomerTier | None] = mapped_column(
        enum_col(CustomerTier), nullable=True
    )
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, default="USD")
    rules: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    valid_from: Mapped[date | None] = mapped_column(nullable=True)
    valid_to: Mapped[date | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
