"""Table 18/33 — approval_decisions."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import ApprovalDecisionType, RoleCode, enum_col
from app.models.base import (
    Base,
    CreatedAtMixin,
    JsonDict,
    LongText,
    OrgOwnedMixin,
    Str255,
    UUIDPrimaryKeyMixin,
)


class ApprovalDecision(UUIDPrimaryKeyMixin, OrgOwnedMixin, CreatedAtMixin, Base):
    """Append-only record of who decided what, when, and why.

    Never updated or deleted — a superseded decision stays on the record and is
    marked stale at the request/step level instead.
    """

    __tablename__ = "approval_decisions"
    __table_args__ = (
        sa.Index(
            "ix_approval_decisions_approval_request_id_decided_at",
            "approval_request_id",
            "decided_at",
        ),
    )

    approval_request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("approval_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approval_step_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("approval_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quote_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision: Mapped[ApprovalDecisionType] = mapped_column(
        enum_col(ApprovalDecisionType), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    actor_role: Mapped[RoleCode] = mapped_column(enum_col(RoleCode), nullable=False)
    actor_email: Mapped[Str255] = mapped_column(nullable=False)
    reason: Mapped[LongText] = mapped_column(nullable=False)
    #: Financial state the approver was actually looking at.
    decision_snapshot: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)
    decided_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("timezone('utc', now())"),
    )
