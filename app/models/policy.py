"""Table 13/33 — policies."""

from __future__ import annotations

import uuid
from datetime import date

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import (
    ApprovalLevel,
    CustomerTier,
    PolicyComparison,
    PolicyType,
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
    Str64,
    Str255,
    TimestampMixin,
    UnitMoney,
    UUIDPrimaryKeyMixin,
)


class Policy(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """A governance rule evaluated by the PolicyEngine.

    Approval routing is derived from ``required_action`` on the policies that
    actually fire — never hardcoded. Scope columns are all nullable and act as
    an AND-filter: ``NULL`` means "applies to everything".
    """

    __tablename__ = "policies"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id", "code", name="uq_policies_organization_id_code"
        ),
        sa.Index(
            "ix_policies_organization_id_policy_type_is_active",
            "organization_id",
            "policy_type",
            "is_active",
        ),
    )

    code: Mapped[Str64] = mapped_column(nullable=False)
    name: Mapped[Str255] = mapped_column(nullable=False)
    description: Mapped[LongText | None] = mapped_column(nullable=True)
    policy_type: Mapped[PolicyType] = mapped_column(enum_col(PolicyType), nullable=False)

    # --------------------------------------------------------------- scope
    customer_tier: Mapped[CustomerTier | None] = mapped_column(
        enum_col(CustomerTier), nullable=True
    )
    product_category: Mapped[ProductCategory | None] = mapped_column(
        enum_col(ProductCategory), nullable=True
    )
    customer_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("customer_profiles.id", ondelete="CASCADE"),
        nullable=True,
    )

    # ----------------------------------------------------------- threshold
    threshold_value: Mapped[UnitMoney] = mapped_column(nullable=False)
    comparison: Mapped[PolicyComparison] = mapped_column(
        enum_col(PolicyComparison), nullable=False, default=PolicyComparison.LTE
    )
    unit: Mapped[PolicyUnit] = mapped_column(
        enum_col(PolicyUnit), nullable=False, default=PolicyUnit.PERCENT
    )

    # ------------------------------------------------------------ outcome
    required_action: Mapped[ApprovalLevel] = mapped_column(
        enum_col(ApprovalLevel), nullable=False, default=ApprovalLevel.SALES_MANAGER
    )
    severity: Mapped[Severity] = mapped_column(
        enum_col(Severity), nullable=False, default=Severity.MEDIUM
    )
    #: Lower number wins when two policies match the same scope.
    priority: Mapped[int] = mapped_column(nullable=False, default=100)

    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    effective_from: Mapped[date | None] = mapped_column(nullable=True)
    effective_to: Mapped[date | None] = mapped_column(nullable=True)
    config: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)

    @property
    def specificity(self) -> int:
        """How narrowly scoped this policy is — used for tie-breaking."""
        score = 0
        if self.customer_profile_id is not None:
            score += 4
        if self.customer_tier is not None:
            score += 2
        if self.product_category is not None:
            score += 1
        return score
