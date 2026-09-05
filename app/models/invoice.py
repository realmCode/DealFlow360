"""Table 30/33 — invoices."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import InvoiceStatus, enum_col
from app.models.base import (
    Base,
    Money,
    OrgOwnedMixin,
    Str64,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Invoice(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """Generated from a billing schedule (P1 flow, P0 schema)."""

    __tablename__ = "invoices"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id",
            "invoice_number",
            name="uq_invoices_organization_id_invoice_number",
        ),
        sa.CheckConstraint("amount_paid >= 0", name="amount_paid_non_negative"),
        sa.CheckConstraint(
            "amount_paid <= total_amount", name="amount_paid_not_over_total"
        ),
        sa.Index("ix_invoices_organization_id_status", "organization_id", "status"),
    )

    invoice_number: Mapped[Str64] = mapped_column(nullable=False)
    sales_order_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("sales_orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    billing_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("billing_schedules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[InvoiceStatus] = mapped_column(
        enum_col(InvoiceStatus), nullable=False, default=InvoiceStatus.DRAFT
    )
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, default="USD")
    subtotal: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    tax_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    total_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    amount_paid: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))

    issue_date: Mapped[date] = mapped_column(nullable=False)
    due_date: Mapped[date] = mapped_column(nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    @property
    def amount_due(self) -> Decimal:
        return self.total_amount - self.amount_paid
