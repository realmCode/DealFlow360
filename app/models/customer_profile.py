"""Table 5/33 — customer_profiles."""

from __future__ import annotations

import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import CustomerTier, PaymentTerms, enum_col
from app.models.base import (
    Base,
    Money,
    OrgOwnedMixin,
    Percent,
    Str255,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.organization import Organization


class CustomerProfile(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """The commercial relationship between a seller org and a buyer org.

    Holds everything the policy engine needs about *who* is buying: tier,
    payment terms and credit exposure.
    """

    __tablename__ = "customer_profiles"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id",
            "customer_organization_id",
            name="uq_customer_profiles_organization_id_customer_organization_id",
        ),
        sa.CheckConstraint("credit_limit >= 0", name="credit_limit_non_negative"),
        sa.Index("ix_customer_profiles_tier", "tier"),
    )

    customer_organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    primary_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
    )

    display_name: Mapped[Str255] = mapped_column(nullable=False)
    tier: Mapped[CustomerTier] = mapped_column(
        enum_col(CustomerTier), nullable=False, default=CustomerTier.BRONZE
    )
    payment_terms: Mapped[PaymentTerms] = mapped_column(
        enum_col(PaymentTerms), nullable=False, default=PaymentTerms.NET_30
    )
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, default="USD")
    credit_limit: Mapped[Money] = mapped_column(
        nullable=False, default=Decimal("0.00")
    )
    credit_used: Mapped[Money] = mapped_column(nullable=False, default=Decimal("0.00"))
    #: Tax applied to this customer's quotes when the product has no override.
    tax_rate_pct: Mapped[Percent] = mapped_column(
        nullable=False, default=Decimal("0.0000")
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    customer_organization: Mapped[Organization] = relationship(
        foreign_keys=[customer_organization_id], lazy="joined"
    )

    @property
    def credit_available(self) -> Decimal:
        return self.credit_limit - self.credit_used

    @property
    def payment_terms_days(self) -> int:
        mapping = {
            PaymentTerms.PREPAID: 0,
            PaymentTerms.NET_15: 15,
            PaymentTerms.NET_30: 30,
            PaymentTerms.NET_45: 45,
            PaymentTerms.NET_60: 60,
            PaymentTerms.NET_90: 90,
        }
        return mapping[self.payment_terms]
