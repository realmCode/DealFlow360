"""Table 10/33 — quotes."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import QuoteStatus, enum_col
from app.models.base import (
    Base,
    OrgOwnedMixin,
    Str64,
    Str255,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.deal import Deal


class Quote(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """Quote header. All commercial content lives in immutable versions.

    ``current_version_number`` is stored as an integer rather than an FK to
    ``quote_versions`` to avoid a circular foreign key; the current version is
    resolved by ``(quote_id, version_number)`` which is uniquely indexed.
    """

    __tablename__ = "quotes"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id", "quote_number", name="uq_quotes_organization_id_quote_number"
        ),
        sa.Index("ix_quotes_organization_id_status", "organization_id", "status"),
    )

    quote_number: Mapped[Str64] = mapped_column(nullable=False)
    title: Mapped[Str255] = mapped_column(nullable=False)
    deal_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[QuoteStatus] = mapped_column(
        enum_col(QuoteStatus), nullable=False, default=QuoteStatus.OPEN
    )
    current_version_number: Mapped[int] = mapped_column(nullable=False, default=1)

    deal: Mapped[Deal] = relationship(lazy="selectin")
