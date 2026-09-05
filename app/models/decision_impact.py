"""Table 19/33 — decision_impacts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import Severity, enum_col
from app.models.base import (
    Base,
    CreatedAtMixin,
    LongText,
    OrgOwnedMixin,
    Str64,
    Str255,
    UUIDPrimaryKeyMixin,
)


class DecisionImpact(UUIDPrimaryKeyMixin, OrgOwnedMixin, CreatedAtMixin, Base):
    """One field-level change between two quote versions, with its consequence.

    Written by the DecisionFabric. Non-material changes are recorded too, so the
    impact endpoint can show "we looked at this and it did not matter".
    """

    __tablename__ = "decision_impacts"
    __table_args__ = (
        sa.Index(
            "ix_decision_impacts_quote_version_id_material",
            "quote_version_id",
            "material",
        ),
        sa.Index("ix_decision_impacts_organization_id_detected_at", "organization_id", "detected_at"),
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
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    quote_line_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )

    changed_field: Mapped[Str64] = mapped_column(nullable=False)
    subject: Mapped[Str255 | None] = mapped_column(nullable=True)
    #: JSONB (not text) so numeric/None/str old+new values round-trip exactly.
    old_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    material: Mapped[bool] = mapped_column(nullable=False, default=False)
    severity: Mapped[Severity] = mapped_column(
        enum_col(Severity), nullable=False, default=Severity.LOW
    )
    change_reason: Mapped[LongText] = mapped_column(nullable=False)

    affected_entity_type: Mapped[Str64 | None] = mapped_column(nullable=True)
    affected_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    action_required: Mapped[Str64 | None] = mapped_column(nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("timezone('utc', now())"),
    )
