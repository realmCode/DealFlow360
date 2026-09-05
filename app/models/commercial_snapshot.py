"""Table 15/33 — commercial_snapshots."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import CustomerTier, PaymentTerms, enum_col
from app.models.base import (
    Base,
    JsonDict,
    Money,
    OrgOwnedMixin,
    Percent,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class CommercialSnapshot(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """Point-in-time financial truth for a quote version.

    Answers "what was true when this decision was made". Snapshots are appended
    on every calculation; exactly one row per version carries ``is_current``.
    """

    __tablename__ = "commercial_snapshots"
    __table_args__ = (
        sa.Index(
            "ix_commercial_snapshots_quote_version_id_is_current",
            "quote_version_id",
            "is_current",
        ),
    )

    quote_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    gross_revenue: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    total_discount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    revenue: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    tax_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    cost: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    margin: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    margin_pct: Mapped[Percent] = mapped_column(nullable=False, default=Decimal("0.0000"))
    effective_discount_pct: Mapped[Percent] = mapped_column(
        nullable=False, default=Decimal("0.0000")
    )
    one_time_revenue: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    recurring_revenue: Mapped[Money] = mapped_column(
        nullable=False, default=Decimal("0.00")
    )
    blended_risk_score: Mapped[Percent] = mapped_column(
        nullable=False, default=Decimal("0.0000")
    )

    payment_terms: Mapped[PaymentTerms] = mapped_column(
        enum_col(PaymentTerms), nullable=False, default=PaymentTerms.NET_30
    )
    customer_tier: Mapped[CustomerTier] = mapped_column(
        enum_col(CustomerTier), nullable=False, default=CustomerTier.BRONZE
    )

    #: Full line-level detail so a historical decision can be replayed exactly.
    snapshot_json: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True)
    calculated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("timezone('utc', now())"),
    )
