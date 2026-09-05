"""Table 25/33 — fulfillments."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import FulfillmentStatus, enum_col
from app.models.base import (
    Base,
    LongText,
    Money,
    OrgOwnedMixin,
    Str64,
    Str128,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Fulfillment(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """One shipment from one warehouse.

    A multi-warehouse order produces one fulfilment per warehouse, which is
    exactly why the allocation algorithm tries to minimise shipment count.
    """

    __tablename__ = "fulfillments"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id",
            "fulfillment_number",
            name="uq_fulfillments_organization_id_fulfillment_number",
        ),
        sa.Index("ix_fulfillments_sales_order_id_status", "sales_order_id", "status"),
    )

    fulfillment_number: Mapped[Str64] = mapped_column(nullable=False)
    sales_order_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    shipment_sequence: Mapped[int] = mapped_column(nullable=False, default=1)
    status: Mapped[FulfillmentStatus] = mapped_column(
        enum_col(FulfillmentStatus), nullable=False, default=FulfillmentStatus.PENDING
    )
    carrier: Mapped[Str128 | None] = mapped_column(nullable=True)
    tracking_number: Mapped[Str128 | None] = mapped_column(nullable=True)
    shipping_cost: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    shipped_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    notes: Mapped[LongText | None] = mapped_column(nullable=True)
