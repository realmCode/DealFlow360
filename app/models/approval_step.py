"""Table 17/33 — approval_steps."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import ApprovalLevel, ApprovalStepStatus, RoleCode, enum_col
from app.models.base import (
    Base,
    LongText,
    OrgOwnedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class ApprovalStep(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """One ordered gate in an approval workflow (SALES_MANAGER → FINANCE)."""

    __tablename__ = "approval_steps"
    __table_args__ = (
        sa.UniqueConstraint(
            "approval_request_id",
            "sequence",
            name="uq_approval_steps_approval_request_id_sequence",
        ),
        sa.CheckConstraint("sequence >= 1", name="sequence_positive"),
        sa.Index("ix_approval_steps_status_required_role", "status", "required_role"),
    )

    approval_request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("approval_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(nullable=False)
    level: Mapped[ApprovalLevel] = mapped_column(enum_col(ApprovalLevel), nullable=False)
    #: The role a user must hold to act on this step.
    required_role: Mapped[RoleCode] = mapped_column(enum_col(RoleCode), nullable=False)
    status: Mapped[ApprovalStepStatus] = mapped_column(
        enum_col(ApprovalStepStatus), nullable=False, default=ApprovalStepStatus.PENDING
    )
    reason: Mapped[LongText] = mapped_column(nullable=False)

    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decision_reason: Mapped[LongText | None] = mapped_column(nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    @property
    def is_open(self) -> bool:
        return self.status == ApprovalStepStatus.PENDING
