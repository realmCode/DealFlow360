"""Table 33/33 — idempotency_keys."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import IdempotencyStatus, enum_col
from app.models.base import (
    Base,
    JsonDict,
    OrgOwnedMixin,
    Str64,
    Str128,
    Str255,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class IdempotencyKey(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """Replay protection for state-changing endpoints.

    The ``(organization_id, endpoint, key)`` unique constraint is what actually
    enforces at-most-once semantics: two concurrent retries race to INSERT and
    exactly one wins, the loser reads the stored response.

    ``request_hash`` guards against a client reusing a key with a *different*
    body, which would otherwise silently return the wrong result.
    """

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id",
            "endpoint",
            "key",
            name="uq_idempotency_keys_organization_id_endpoint_key",
        ),
        sa.Index("ix_idempotency_keys_expires_at", "expires_at"),
    )

    key: Mapped[Str128] = mapped_column(nullable=False)
    endpoint: Mapped[Str255] = mapped_column(nullable=False)
    method: Mapped[Str64] = mapped_column(nullable=False, default="POST")
    request_hash: Mapped[Str128] = mapped_column(nullable=False)
    status: Mapped[IdempotencyStatus] = mapped_column(
        enum_col(IdempotencyStatus),
        nullable=False,
        default=IdempotencyStatus.IN_PROGRESS,
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    entity_type: Mapped[Str64 | None] = mapped_column(nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    response_status_code: Mapped[int | None] = mapped_column(nullable=True)
    response_body: Mapped[JsonDict | None] = mapped_column(nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
