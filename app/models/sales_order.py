"""Table 23/33 — sales_orders."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import PaymentTerms, SalesOrderStatus, enum_col
from app.models.base import (
    Base,
    Money,
    OrgOwnedMixin,
    Percent,
    Str64,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class SalesOrder(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """Order created by confirming an approved quote version.

    ``quote_version_id`` is **UNIQUE**: the database itself guarantees that one
    confirmed version can never produce two orders, independently of the
    application-level idempotency layer.
    """

    __tablename__ = "sales_orders"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id",
            "order_number",
            name="uq_sales_orders_organization_id_order_number",
        ),
        sa.UniqueConstraint(
            "quote_version_id", name="uq_sales_orders_quote_version_id"
        ),
        sa.Index("ix_sales_orders_organization_id_status", "organization_id", "status"),
        sa.Index(
            "ix_sales_orders_customer_organization_id", "customer_organization_id"
        ),
    )

    order_number: Mapped[Str64] = mapped_column(nullable=False)
    deal_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("deals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quotes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quote_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_profile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("customer_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[SalesOrderStatus] = mapped_column(
        enum_col(SalesOrderStatus), nullable=False, default=SalesOrderStatus.CREATED
    )
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, default="USD")
    payment_terms: Mapped[PaymentTerms] = mapped_column(
        enum_col(PaymentTerms), nullable=False, default=PaymentTerms.NET_30
    )

    gross_revenue: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    total_discount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    subtotal: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    tax_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    total_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    total_cost: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    margin: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    margin_pct: Mapped[Percent] = mapped_column(nullable=False, default=Decimal("0.0000"))
    one_time_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    recurring_amount: Mapped[Money] = mapped_column(
        nullable=False, default=Decimal("0.00")
    )

    confirmed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("timezone('utc', now())"),
    )
    fully_allocated: Mapped[bool] = mapped_column(nullable=False, default=False)
    has_backorder: Mapped[bool] = mapped_column(nullable=False, default=False)
    allocated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    fulfilled_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
