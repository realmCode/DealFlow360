"""Table 14/33 — policy_results."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import (
    ApprovalLevel,
    CustomerTier,
    PolicyResultStatus,
    PolicyUnit,
    ProductCategory,
    Severity,
    enum_col,
)
from app.models.base import (
    Base,
    JsonDict,
    LongText,
    OrgOwnedMixin,
    Percent,
    Str64,
    Str255,
    TimestampMixin,
    UnitMoney,
    UUIDPrimaryKeyMixin,
)


class PolicyResult(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """A single explainable policy evaluation against one quote version.

    Results are replaced (not appended) each time a version is evaluated, so
    ``GET /quote-versions/{id}/policy-results`` always reflects current truth.
    """

    __tablename__ = "policy_results"
    __table_args__ = (
        sa.Index(
            "ix_policy_results_quote_version_id_status", "quote_version_id", "status"
        ),
        sa.Index("ix_policy_results_organization_id_rule", "organization_id", "rule"),
    )

    quote_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    quote_line_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_lines.id", ondelete="CASCADE"),
        nullable=True,
    )

    rule: Mapped[Str64] = mapped_column(nullable=False)
    status: Mapped[PolicyResultStatus] = mapped_column(
        enum_col(PolicyResultStatus), nullable=False
    )
    subject: Mapped[Str255 | None] = mapped_column(nullable=True)

    actual_value: Mapped[UnitMoney] = mapped_column(nullable=False, default=Decimal("0"))
    threshold_value: Mapped[UnitMoney] = mapped_column(
        nullable=False, default=Decimal("0")
    )
    #: Percentage points (or currency units) by which the threshold was missed.
    overage_points: Mapped[UnitMoney] = mapped_column(
        nullable=False, default=Decimal("0")
    )
    unit: Mapped[PolicyUnit] = mapped_column(
        enum_col(PolicyUnit), nullable=False, default=PolicyUnit.PERCENT
    )

    scope_category: Mapped[ProductCategory | None] = mapped_column(
        enum_col(ProductCategory), nullable=True
    )
    scope_tier: Mapped[CustomerTier | None] = mapped_column(
        enum_col(CustomerTier), nullable=True
    )

    #: Always human-readable. Never just a number.
    reason: Mapped[LongText] = mapped_column(nullable=False)
    required_action: Mapped[ApprovalLevel | None] = mapped_column(
        enum_col(ApprovalLevel), nullable=True
    )
    severity: Mapped[Severity] = mapped_column(
        enum_col(Severity), nullable=False, default=Severity.LOW
    )
    #: This result's contribution to the blended risk score (auditable maths).
    risk_contribution: Mapped[Percent] = mapped_column(
        nullable=False, default=Decimal("0.0000")
    )
    detail: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)
    evaluated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("timezone('utc', now())"),
    )
