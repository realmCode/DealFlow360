"""Table 22/33 — negotiation_messages."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import AuthorKind, NegotiationMessageType, enum_col
from app.models.base import (
    Base,
    CreatedAtMixin,
    JsonDict,
    LongText,
    OrgOwnedMixin,
    Percent,
    Quantity,
    Str255,
    UnitMoney,
    UUIDPrimaryKeyMixin,
)


class NegotiationMessage(UUIDPrimaryKeyMixin, OrgOwnedMixin, CreatedAtMixin, Base):
    """Append-only message. A COUNTER_OFFER carries the requested terms.

    Counter-offers never mutate the version they are posted against; the
    negotiation service creates the next version from the request instead.
    """

    __tablename__ = "negotiation_messages"
    __table_args__ = (
        sa.Index(
            "ix_negotiation_messages_thread_id_created_at", "thread_id", "created_at"
        ),
        sa.CheckConstraint(
            "requested_discount_pct IS NULL OR "
            "(requested_discount_pct >= 0 AND requested_discount_pct <= 100)",
            name="requested_discount_pct_range",
        ),
        sa.CheckConstraint(
            "requested_quantity IS NULL OR requested_quantity > 0",
            name="requested_quantity_positive",
        ),
    )

    thread_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("negotiation_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quote_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quote_line_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    author_kind: Mapped[AuthorKind] = mapped_column(enum_col(AuthorKind), nullable=False)
    author_display_name: Mapped[Str255] = mapped_column(nullable=False)
    message_type: Mapped[NegotiationMessageType] = mapped_column(
        enum_col(NegotiationMessageType), nullable=False
    )
    body: Mapped[LongText] = mapped_column(nullable=False)

    # ------------------------------------------------- counter-offer terms
    requested_discount_pct: Mapped[Percent | None] = mapped_column(nullable=True)
    requested_quantity: Mapped[Quantity | None] = mapped_column(nullable=True)
    requested_unit_price: Mapped[UnitMoney | None] = mapped_column(nullable=True)
    payload: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)

    #: Version created as a direct result of this message (counter-offers).
    triggered_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
