"""Table 27/33 — inventory."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    OrgOwnedMixin,
    Quantity,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Inventory(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """Stock level for one product in one warehouse.

    Available stock is ``quantity_on_hand - quantity_reserved``. A database
    CHECK constraint makes over-reservation impossible even if application code
    has a bug: the row simply refuses to be written.

    Variant-level stock is P1; today inventory is tracked per product.
    """

    __tablename__ = "inventory"
    __table_args__ = (
        sa.UniqueConstraint(
            "warehouse_id", "product_id", name="uq_inventory_warehouse_id_product_id"
        ),
        sa.CheckConstraint("quantity_on_hand >= 0", name="quantity_on_hand_non_negative"),
        sa.CheckConstraint("quantity_reserved >= 0", name="quantity_reserved_non_negative"),
        sa.CheckConstraint(
            "quantity_reserved <= quantity_on_hand", name="no_over_reservation"
        ),
        sa.Index("ix_inventory_organization_id_product_id", "organization_id", "product_id"),
    )

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=True,
    )

    quantity_on_hand: Mapped[Quantity] = mapped_column(
        nullable=False, default=Decimal("0")
    )
    quantity_reserved: Mapped[Quantity] = mapped_column(
        nullable=False, default=Decimal("0")
    )
    quantity_inbound: Mapped[Quantity] = mapped_column(
        nullable=False, default=Decimal("0")
    )
    reorder_point: Mapped[Quantity] = mapped_column(nullable=False, default=Decimal("0"))
    expected_restock_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    @property
    def quantity_available(self) -> Decimal:
        return self.quantity_on_hand - self.quantity_reserved
