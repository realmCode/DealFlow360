"""Table 11/33 — quote_versions."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import (
    EDITABLE_VERSION_STATUSES,
    PaymentTerms,
    QuoteVersionSource,
    QuoteVersionStatus,
    REVISABLE_VERSION_STATUSES,
    RiskBand,
    TERMINAL_VERSION_STATUSES,
    enum_col,
)
from app.models.base import (
    Base,
    LongText,
    Money,
    OrgOwnedMixin,
    Percent,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.quote import Quote


class QuoteVersion(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """An immutable commercial snapshot of a quote.

    Only ``DRAFT`` versions accept line edits. Every other state requires a
    revision, which creates the next version and supersedes this one. The
    denormalised financial columns are written **only** by
    :class:`app.services.commercial_engine.CommercialEngine`.
    """

    __tablename__ = "quote_versions"
    __table_args__ = (
        sa.UniqueConstraint(
            "quote_id", "version_number", name="uq_quote_versions_quote_id_version_number"
        ),
        sa.CheckConstraint("version_number >= 1", name="version_number_positive"),
        sa.Index("ix_quote_versions_organization_id_status", "organization_id", "status"),
        sa.Index("ix_quote_versions_quote_id_status", "quote_id", "status"),
    )

    quote_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(nullable=False, default=1)
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[QuoteVersionStatus] = mapped_column(
        enum_col(QuoteVersionStatus), nullable=False, default=QuoteVersionStatus.DRAFT
    )
    source: Mapped[QuoteVersionSource] = mapped_column(
        enum_col(QuoteVersionSource), nullable=False, default=QuoteVersionSource.INITIAL
    )
    revision_reason: Mapped[LongText | None] = mapped_column(nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # ---------------------------------------------------- commercial terms
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, default="USD")
    payment_terms: Mapped[PaymentTerms] = mapped_column(
        enum_col(PaymentTerms), nullable=False, default=PaymentTerms.NET_30
    )
    valid_until: Mapped[date | None] = mapped_column(nullable=True)

    # -------------------------- authoritative totals (backend-calculated)
    gross_revenue: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    total_discount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    net_revenue: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    tax_amount: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    total_revenue: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    total_cost: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    margin: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    margin_pct: Mapped[Percent] = mapped_column(nullable=False, default=Decimal("0.0000"))
    effective_discount_pct: Mapped[Percent] = mapped_column(
        nullable=False, default=Decimal("0.0000")
    )
    one_time_revenue: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    recurring_revenue: Mapped[Money] = mapped_column(
        nullable=False, default=Decimal("0.00")
    )

    # ---------------------------------------------------------------- risk
    blended_risk_score: Mapped[Percent] = mapped_column(
        nullable=False, default=Decimal("0.0000")
    )
    risk_band: Mapped[RiskBand] = mapped_column(
        enum_col(RiskBand), nullable=False, default=RiskBand.NONE
    )
    requires_approval: Mapped[bool] = mapped_column(nullable=False, default=False)
    #: Set when a material change invalidated an approval on this version.
    is_stale: Mapped[bool] = mapped_column(nullable=False, default=False)
    stale_reason: Mapped[LongText | None] = mapped_column(nullable=True)

    # ------------------------------------------------------- state stamps
    calculated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    superseded_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    quote: Mapped[Quote] = relationship(lazy="selectin")

    # ------------------------------------------------------------ helpers
    @property
    def is_editable(self) -> bool:
        return self.status in EDITABLE_VERSION_STATUSES

    @property
    def is_revisable(self) -> bool:
        return self.status in REVISABLE_VERSION_STATUSES

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_VERSION_STATUSES
