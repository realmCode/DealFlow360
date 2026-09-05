"""Table 29/33 — billing_schedules."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import (
    BillingScheduleStatus,
    BillingType,
    RecurringInterval,
    enum_col,
)
from app.models.base import (
    Base,
    Factor,
    JsonDict,
    Money,
    OrgOwnedMixin,
    Str64,
    Str255,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class BillingSchedule(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """A billing obligation derived from an order line.

    One-time lines produce a single ``ONE_TIME`` schedule. Recurring lines
    produce one row per period so proration, mid-term changes and revenue
    recognition are all expressible without recomputation.
    """

    __tablename__ = "billing_schedules"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id",
            "schedule_number",
            name="uq_billing_schedules_organization_id_schedule_number",
        ),
        sa.CheckConstraint("amount >= 0", name="amount_non_negative"),
        sa.CheckConstraint("period_number >= 1", name="period_number_positive"),
        sa.CheckConstraint("total_periods >= 1", name="total_periods_positive"),
        sa.CheckConstraint(
            "(billing_type = 'RECURRING' AND recurring_interval IS NOT NULL) OR "
            "(billing_type = 'ONE_TIME' AND recurring_interval IS NULL)",
            name="recurring_requires_interval",
        ),
        sa.Index(
            "ix_billing_schedules_sales_order_id_billing_type",
            "sales_order_id",
            "billing_type",
        ),
        sa.Index(
            "ix_billing_schedules_organization_id_status_due_date",
            "organization_id",
            "status",
            "due_date",
        ),
    )

    schedule_number: Mapped[Str64] = mapped_column(nullable=False)
    sales_order_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: NULL only for order-level charges; line-derived schedules always set it.
    sales_order_line_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("sales_order_lines.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    billing_type: Mapped[BillingType] = mapped_column(
        enum_col(BillingType), nullable=False
    )
    recurring_interval: Mapped[RecurringInterval | None] = mapped_column(
        enum_col(RecurringInterval), nullable=True
    )
    status: Mapped[BillingScheduleStatus] = mapped_column(
        enum_col(BillingScheduleStatus),
        nullable=False,
        default=BillingScheduleStatus.SCHEDULED,
    )
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, default="USD")

    #: Net amount billed for this period (tax excluded).
    amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    tax_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    total_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))

    period_number: Mapped[int] = mapped_column(nullable=False, default=1)
    total_periods: Mapped[int] = mapped_column(nullable=False, default=1)
    period_start: Mapped[date] = mapped_column(nullable=False)
    period_end: Mapped[date] = mapped_column(nullable=False)
    due_date: Mapped[date] = mapped_column(nullable=False)

    is_prorated: Mapped[bool] = mapped_column(nullable=False, default=False)
    proration_factor: Mapped[Factor] = mapped_column(
        nullable=False, default=Decimal("1.00000000")
    )
    description: Mapped[Str255] = mapped_column(nullable=False)
    detail: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)
