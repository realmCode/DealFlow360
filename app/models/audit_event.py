"""Table 32/33 — audit_events."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import RoleCode, enum_col
from app.models.base import (
    Base,
    CreatedAtMixin,
    JsonDict,
    Str64,
    Str255,
    UUIDPrimaryKeyMixin,
)


class AuditEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only business event log.

    Deliberately *not* org-owned via ``OrgOwnedMixin``: signup and login happen
    before an org context is fully resolved, so ``organization_id`` is nullable.

    ``sequence`` is a monotonic bigint that gives a stable total ordering even
    when several events share the same microsecond — which they do, because a
    single transaction can emit half a dozen.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        sa.Index(
            "ix_audit_events_organization_id_occurred_at",
            "organization_id",
            "occurred_at",
        ),
        sa.Index("ix_audit_events_entity_type_entity_id", "entity_type", "entity_id"),
        sa.Index("ix_audit_events_event_type", "event_type"),
        sa.Index("ix_audit_events_actor_user_id", "actor_user_id"),
    )

    sequence: Mapped[int] = mapped_column(
        sa.BigInteger, sa.Identity(always=False), nullable=False, unique=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[Str64] = mapped_column(nullable=False)
    entity_type: Mapped[Str64] = mapped_column(nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_role: Mapped[RoleCode | None] = mapped_column(
        enum_col(RoleCode), nullable=True
    )
    actor_email: Mapped[Str255 | None] = mapped_column(nullable=True)

    payload: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)
    ip_address: Mapped[Str64 | None] = mapped_column(nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("timezone('utc', now())"),
        index=True,
    )
