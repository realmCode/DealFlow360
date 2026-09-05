"""Table 21/33 — negotiation_threads."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import NegotiationThreadStatus, enum_col
from app.models.base import (
    Base,
    OrgOwnedMixin,
    Str255,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class NegotiationThread(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """Portal conversation for one quote. Exactly one thread per quote.

    ``customer_organization_id`` is the authorization boundary for portal
    users — it is checked on every portal read and write.
    """

    __tablename__ = "negotiation_threads"
    __table_args__ = (
        sa.UniqueConstraint("quote_id", name="uq_negotiation_threads_quote_id"),
        sa.Index(
            "ix_negotiation_threads_customer_organization_id_status",
            "customer_organization_id",
            "status",
        ),
    )

    quote_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Version currently under discussion (advances as revisions are created).
    quote_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject: Mapped[Str255] = mapped_column(nullable=False)
    status: Mapped[NegotiationThreadStatus] = mapped_column(
        enum_col(NegotiationThreadStatus),
        nullable=False,
        default=NegotiationThreadStatus.OPEN,
    )
    opened_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
