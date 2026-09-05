"""Table 9/33 — deals."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import DealStage, enum_col
from app.models.base import (
    Base,
    LongText,
    Money,
    OrgOwnedMixin,
    Str64,
    Str255,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.customer_profile import CustomerProfile


class Deal(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """Top-level container. One deal can carry several quotes over time."""

    __tablename__ = "deals"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id", "reference", name="uq_deals_organization_id_reference"
        ),
        sa.Index("ix_deals_organization_id_stage", "organization_id", "stage"),
        sa.Index("ix_deals_owner_user_id", "owner_user_id"),
    )

    reference: Mapped[Str64] = mapped_column(nullable=False)
    name: Mapped[Str255] = mapped_column(nullable=False)
    customer_profile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("customer_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    primary_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
    )

    stage: Mapped[DealStage] = mapped_column(
        enum_col(DealStage), nullable=False, default=DealStage.QUALIFICATION
    )
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, default="USD")
    expected_value: Mapped[Money] = mapped_column(
        nullable=False, default=Decimal("0.00")
    )
    expected_close_date: Mapped[date | None] = mapped_column(nullable=True)
    notes: Mapped[LongText | None] = mapped_column(nullable=True)

    customer_profile: Mapped[CustomerProfile] = relationship(lazy="selectin")
