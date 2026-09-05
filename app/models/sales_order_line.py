"""Table 24/33 — sales_order_lines."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import BillingType, ProductCategory, RecurringInterval, enum_col
from app.models.base import (
    Base,
    Money,
    OrgOwnedMixin,
    Percent,
    Quantity,
    Str255,
    TimestampMixin,
    UnitMoney,
    UUIDPrimaryKeyMixin,
)


class SalesOrderLine(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """Frozen copy of a confirmed quote line, plus execution counters.

    One-time and recurring lines coexist on the same order; ``billing_type``
    drives which kind of billing schedule the BillingService produces.
    """

    __tablename__ = "sales_order_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "sales_order_id",
            "line_number",
            name="uq_sales_order_lines_sales_order_id_line_number",
        ),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint(
            "quantity_allocated >= 0 AND quantity_allocated <= quantity",
            name="quantity_allocated_within_bounds",
        ),
        sa.CheckConstraint(
            "quantity_fulfilled >= 0 AND quantity_fulfilled <= quantity",
            name="quantity_fulfilled_within_bounds",
        ),
        sa.CheckConstraint(
            "quantity_backordered >= 0", name="quantity_backordered_non_negative"
        ),
        sa.Index("ix_sales_order_lines_product_id", "product_id"),
    )

    sales_order_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quote_line_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(nullable=False)
    description: Mapped[Str255] = mapped_column(nullable=False)
    category: Mapped[ProductCategory] = mapped_column(
        enum_col(ProductCategory), nullable=False
    )

    quantity: Mapped[Quantity] = mapped_column(nullable=False)
    unit_list_price: Mapped[UnitMoney] = mapped_column(nullable=False)
    unit_net_price: Mapped[UnitMoney] = mapped_column(nullable=False)
    unit_cost: Mapped[UnitMoney] = mapped_column(nullable=False)
    discount_pct: Mapped[Percent] = mapped_column(nullable=False, default=Decimal("0.0000"))
    discount_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    gross_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    net_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    tax_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    total_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    line_cost: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))

    billing_type: Mapped[BillingType] = mapped_column(
        enum_col(BillingType), nullable=False, default=BillingType.ONE_TIME
    )
    recurring_interval: Mapped[RecurringInterval | None] = mapped_column(
        enum_col(RecurringInterval), nullable=True
    )
    recurring_periods: Mapped[int] = mapped_column(nullable=False, default=1)

    is_stock_tracked: Mapped[bool] = mapped_column(nullable=False, default=False)
    #: Per-line override of the order's promised delivery date, for orders
    #: where hardware and services land on different dates.
    promised_delivery_date: Mapped[date | None] = mapped_column(
        sa.Date, nullable=True
    )

    quantity_allocated: Mapped[Quantity] = mapped_column(
        nullable=False, default=Decimal("0")
    )
    quantity_backordered: Mapped[Quantity] = mapped_column(
        nullable=False, default=Decimal("0")
    )
    quantity_fulfilled: Mapped[Quantity] = mapped_column(
        nullable=False, default=Decimal("0")
    )

    @property
    def quantity_outstanding(self) -> Decimal:
        return self.quantity - self.quantity_allocated
