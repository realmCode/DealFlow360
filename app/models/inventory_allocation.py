"""Table 28/33 — inventory_allocations."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import AllocationMode, AllocationStatus, enum_col
from app.models.base import (
    Base,
    LongText,
    OrgOwnedMixin,
    Quantity,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class InventoryAllocation(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """Reservation of stock from one warehouse against one order line.

    A backordered allocation has ``warehouse_id IS NULL`` — nothing is reserved
    because nothing exists yet; it records demand awaiting restock.
    """

    __tablename__ = "inventory_allocations"
    __table_args__ = (
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint(
            "(status = 'BACKORDERED' AND warehouse_id IS NULL) OR "
            "(status <> 'BACKORDERED' AND warehouse_id IS NOT NULL)",
            name="backorder_has_no_warehouse",
        ),
        sa.Index(
            "ix_inventory_allocations_sales_order_id_status",
            "sales_order_id",
            "status",
        ),
        sa.Index(
            "ix_inventory_allocations_warehouse_id_product_id",
            "warehouse_id",
            "product_id",
        ),
    )

    sales_order_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sales_order_line_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("sales_order_lines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=True,
    )
    inventory_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("inventory.id", ondelete="SET NULL"),
        nullable=True,
    )
    fulfillment_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("fulfillments.id", ondelete="SET NULL"),
        nullable=True,
    )

    quantity: Mapped[Quantity] = mapped_column(nullable=False)
    status: Mapped[AllocationStatus] = mapped_column(
        enum_col(AllocationStatus), nullable=False, default=AllocationStatus.RESERVED
    )
    mode: Mapped[AllocationMode] = mapped_column(
        enum_col(AllocationMode), nullable=False, default=AllocationMode.AUTOMATIC
    )
    allocated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    allocated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("timezone('utc', now())"),
    )
    released_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    expected_available_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    notes: Mapped[LongText | None] = mapped_column(nullable=True)
