"""Table 26/33 — warehouses."""

from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    Money,
    OrgOwnedMixin,
    Str64,
    Str128,
    Str255,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Warehouse(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """A fulfilment location.

    ``priority`` and ``shipping_cost_per_shipment`` are the inputs the
    allocation algorithm uses to break ties between warehouses that could both
    serve a line — no warehouse is special-cased in code.
    """

    __tablename__ = "warehouses"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id", "code", name="uq_warehouses_organization_id_code"
        ),
        sa.CheckConstraint(
            "shipping_cost_per_shipment >= 0", name="shipping_cost_non_negative"
        ),
    )

    code: Mapped[Str64] = mapped_column(nullable=False)
    name: Mapped[Str255] = mapped_column(nullable=False)
    region: Mapped[Str128 | None] = mapped_column(nullable=True)
    address_line1: Mapped[Str255 | None] = mapped_column(nullable=True)
    city: Mapped[Str128 | None] = mapped_column(nullable=True)
    country: Mapped[Str64 | None] = mapped_column(nullable=True)
    postal_code: Mapped[Str64 | None] = mapped_column(nullable=True)
    #: Lower value = preferred when availability and shipment count tie.
    priority: Mapped[int] = mapped_column(nullable=False, default=100)
    shipping_cost_per_shipment: Mapped[Money] = mapped_column(
        nullable=False, default=Decimal("0.00")
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
