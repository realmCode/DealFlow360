"""Table 20/33 — attention_items."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import (
    AttentionItemStatus,
    AttentionItemType,
    RoleCode,
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
    UUIDPrimaryKeyMixin,
)


class AttentionItem(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """Control Tower row. Action-oriented, not a metric.

    Every item answers four questions: WHY (``reason``), IMPACT (``impact``),
    OWNER (``owner_role``/``owner_user_id``) and WHAT NEXT
    (``recommended_action``).

    The partial unique index keeps the queue clean: one live item per
    (source, type). Once resolved, the same situation can raise a new item.
    """

    __tablename__ = "attention_items"
    __table_args__ = (
        sa.Index(
            "ix_attention_items_organization_id_status_severity",
            "organization_id",
            "status",
            "severity",
        ),
        sa.Index("ix_attention_items_source_type_source_id", "source_type", "source_id"),
        sa.Index("ix_attention_items_owner_role_status", "owner_role", "status"),
        sa.Index(
            "uq_attention_items_live_per_source",
            "organization_id",
            "source_type",
            "source_id",
            "type",
            unique=True,
            postgresql_where=sa.text("status <> 'RESOLVED'"),
        ),
    )

    source_type: Mapped[Str64] = mapped_column(nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    type: Mapped[AttentionItemType] = mapped_column(
        enum_col(AttentionItemType), nullable=False
    )
    severity: Mapped[Severity] = mapped_column(enum_col(Severity), nullable=False)

    title: Mapped[Str255] = mapped_column(nullable=False)
    reason: Mapped[LongText] = mapped_column(nullable=False)
    impact: Mapped[LongText] = mapped_column(nullable=False)
    recommended_action: Mapped[LongText] = mapped_column(nullable=False)

    owner_role: Mapped[RoleCode] = mapped_column(enum_col(RoleCode), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[AttentionItemStatus] = mapped_column(
        enum_col(AttentionItemStatus), nullable=False, default=AttentionItemStatus.OPEN
    )
    #: Correlation ids so the frontend can deep-link straight to the blocker.
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("deals.id", ondelete="CASCADE"), nullable=True
    )
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), sa.ForeignKey("quotes.id", ondelete="CASCADE"), nullable=True
    )
    detail: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)

    resolved_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolution_note: Mapped[LongText | None] = mapped_column(nullable=True)
