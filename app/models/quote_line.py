"""Table 12/33 — quote_lines."""

from __future__ import annotations

import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import BillingType, ProductCategory, RecurringInterval, enum_col
from app.models.base import (
    Base,
    LongText,
    Money,
    OrgOwnedMixin,
    Percent,
    Quantity,
    Str255,
    TimestampMixin,
    UnitMoney,
    UUIDPrimaryKeyMixin,
)
from app.models.product import Product


class QuoteLine(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """A single priced line inside one quote version.

    ``unit_list_price``/``unit_cost``/``category``/``billing_type`` are copied
    from the product at line creation so that a later catalog change cannot
    silently rewrite the commercial history of an approved quote.

    Every ``*_amount``/``line_*`` column is derived output owned by the
    CommercialEngine; clients only ever send quantity, discount and overrides.
    """

    __tablename__ = "quote_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "quote_version_id",
            "line_number",
            name="uq_quote_lines_quote_version_id_line_number",
        ),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint(
            "discount_pct >= 0 AND discount_pct <= 100", name="discount_pct_range"
        ),
        sa.CheckConstraint("unit_list_price >= 0", name="unit_list_price_non_negative"),
        sa.CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
        sa.CheckConstraint("recurring_periods >= 1", name="recurring_periods_positive"),
        sa.Index("ix_quote_lines_product_id", "product_id"),
    )

    quote_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
    )
    line_number: Mapped[int] = mapped_column(nullable=False)
    description: Mapped[Str255] = mapped_column(nullable=False)
    notes: Mapped[LongText | None] = mapped_column(nullable=True)

    #: The line on the parent version this one was cloned from.
    #:
    #: The Decision Fabric matches lines across versions through this link
    #: rather than by ``line_number``. Position-based matching silently
    #: conflates "line 4 removed" plus "new line added at slot 4" into a single
    #: bogus product change, which would hide a real scope change from the
    #: approver. ``NULL`` therefore means genuinely new on this version.
    source_line_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_lines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ------------------------------------------------------------- inputs
    category: Mapped[ProductCategory] = mapped_column(
        enum_col(ProductCategory), nullable=False
    )
    quantity: Mapped[Quantity] = mapped_column(nullable=False, default=Decimal("1"))
    unit_list_price: Mapped[UnitMoney] = mapped_column(nullable=False)
    unit_cost: Mapped[UnitMoney] = mapped_column(nullable=False)
    discount_pct: Mapped[Percent] = mapped_column(nullable=False, default=Decimal("0.0000"))
    tax_rate_pct: Mapped[Percent] = mapped_column(nullable=False, default=Decimal("0.0000"))

    billing_type: Mapped[BillingType] = mapped_column(
        enum_col(BillingType), nullable=False, default=BillingType.ONE_TIME
    )
    recurring_interval: Mapped[RecurringInterval | None] = mapped_column(
        enum_col(RecurringInterval), nullable=True
    )
    recurring_periods: Mapped[int] = mapped_column(nullable=False, default=1)
    is_stock_tracked: Mapped[bool] = mapped_column(nullable=False, default=False)

    # -------------------------------------------- derived (engine-owned)
    unit_net_price: Mapped[UnitMoney] = mapped_column(
        nullable=False, default=Decimal("0.0000")
    )
    gross_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    discount_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    net_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    tax_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    total_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    line_cost: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    line_margin: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    line_margin_pct: Mapped[Percent] = mapped_column(
        nullable=False, default=Decimal("0.0000")
    )

    product: Mapped[Product] = relationship(lazy="selectin")
