"""Table 16/33 — approval_requests."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import ApprovalRequestStatus, enum_col
from app.models.base import (
    Base,
    JsonDict,
    LongText,
    OrgOwnedMixin,
    Percent,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class ApprovalRequest(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """Header for one approval workflow over one quote version.

    A version may accumulate several requests over its life: the original, plus
    a fresh one each time a material change makes the previous decision stale.
    Only one request per version may be ``PENDING`` at a time (partial unique
    index below).
    """

    __tablename__ = "approval_requests"
    __table_args__ = (
        sa.Index(
            "ix_approval_requests_organization_id_status", "organization_id", "status"
        ),
        sa.Index("ix_approval_requests_quote_id_status", "quote_id", "status"),
        sa.Index(
            "uq_approval_requests_one_pending_per_version",
            "quote_version_id",
            unique=True,
            postgresql_where=sa.text("status = 'PENDING'"),
        ),
    )

    quote_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quote_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ApprovalRequestStatus] = mapped_column(
        enum_col(ApprovalRequestStatus),
        nullable=False,
        default=ApprovalRequestStatus.PENDING,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reason: Mapped[LongText] = mapped_column(nullable=False)

    #: ``[{"type": "FINANCE", "reason": "..."}]`` — routing decision as evaluated.
    required_levels: Mapped[list[Any]] = mapped_column(nullable=False, default=list)
    policy_summary: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)
    blended_risk_score: Mapped[Percent] = mapped_column(
        nullable=False, default=Decimal("0.0000")
    )
    current_step_sequence: Mapped[int] = mapped_column(nullable=False, default=1)

    decided_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    stale_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    stale_reason: Mapped[LongText | None] = mapped_column(nullable=True)
    superseded_by_request_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("approval_requests.id", ondelete="SET NULL"),
        nullable=True,
    )

    @property
    def is_open(self) -> bool:
        return self.status == ApprovalRequestStatus.PENDING
