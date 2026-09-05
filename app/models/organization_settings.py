"""Table 34 — organization_settings.

PDF A3 requires the approval chain to be configurable, and B9 requires the
stalled-deal window to be a *configured* number of days. Both were previously
process-global environment variables, which cannot satisfy "configurable" in a
multi-tenant system: two organizations on one deployment could not disagree.

One row per organization, created lazily from the `app.config` defaults on first
access so existing tenants keep their current behaviour exactly.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    Percent,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class OrganizationSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-tenant governance tunables.

    Deliberately *not* using ``OrgOwnedMixin``: that mixin models "a row owned
    by a tenant", of which there are many. This is exactly one row per tenant,
    so ``organization_id`` carries a UNIQUE constraint instead.
    """

    __tablename__ = "organization_settings"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id", name="uq_organization_settings_organization_id"
        ),
        sa.CheckConstraint("stalled_deal_days >= 1", name="stalled_deal_days_positive"),
        sa.CheckConstraint(
            "discount_anomaly_min_samples >= 2",
            name="anomaly_min_samples_meaningful",
        ),
        sa.CheckConstraint(
            "discount_anomaly_sigma > 0", name="anomaly_sigma_positive"
        ),
        sa.CheckConstraint("approval_sla_hours >= 1", name="approval_sla_positive"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ------------------------------------------------------- approval chain
    #: Blended risk score at or above which FINANCE is added to the chain,
    #: independently of which policies fired. PDF A3.3.
    finance_escalation_threshold: Mapped[Percent] = mapped_column(
        nullable=False, default=Decimal("60.0"), server_default=sa.text("60.0")
    )

    # -------------------------------------------------------- risk weights
    risk_discount_overage_weight: Mapped[Percent] = mapped_column(
        nullable=False, default=Decimal("3.0"), server_default=sa.text("3.0")
    )
    risk_breadth_weight: Mapped[Percent] = mapped_column(
        nullable=False, default=Decimal("5.0"), server_default=sa.text("5.0")
    )
    risk_margin_weight: Mapped[Percent] = mapped_column(
        nullable=False, default=Decimal("5.0"), server_default=sa.text("5.0")
    )
    risk_depth_weight: Mapped[Percent] = mapped_column(
        nullable=False, default=Decimal("0.4"), server_default=sa.text("0.4")
    )

    # ------------------------------------------------------------- signals
    #: PDF B9.1 — "inactive for more than a configured number of days".
    stalled_deal_days: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=14, server_default=sa.text("14")
    )
    #: PDF B9.2 — how many standard deviations above a rep's own mean counts
    #: as an anomaly.
    discount_anomaly_sigma: Mapped[Percent] = mapped_column(
        nullable=False, default=Decimal("2.0"), server_default=sa.text("2.0")
    )
    #: Below this many prior quotes the baseline is not statistically
    #: meaningful and no anomaly is raised — a new rep must not be flagged on
    #: their first discount.
    discount_anomaly_min_samples: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=5, server_default=sa.text("5")
    )
    #: Hours a pending approval step may wait before it counts as breached.
    approval_sla_hours: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=24, server_default=sa.text("24")
    )
    #: PDF A6.3 — only surface suggestions at or above this margin.
    recommendation_min_margin_pct: Mapped[Percent] = mapped_column(
        nullable=False, default=Decimal("0.0"), server_default=sa.text("0.0")
    )
