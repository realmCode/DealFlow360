"""Table 38 — dismissed_recommendations.

PDF B5 gives the upsell panel a **Dismiss** button alongside Add to Quote.
Without persistence, a dismissed suggestion reappears on the next fetch, which
makes the button appear broken and trains the rep to ignore the panel.

Scoped to the quote version rather than the quote: a revision is a fresh
commercial proposal, so a suggestion declined on v1 is worth offering again on
v2 when the numbers have changed.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    CreatedAtMixin,
    LongText,
    OrgOwnedMixin,
    UUIDPrimaryKeyMixin,
)


class DismissedRecommendation(
    UUIDPrimaryKeyMixin, OrgOwnedMixin, CreatedAtMixin, Base
):
    __tablename__ = "dismissed_recommendations"
    __table_args__ = (
        sa.UniqueConstraint(
            "quote_version_id",
            "product_id",
            name="uq_dismissed_recommendations_quote_version_id_product_id",
        ),
    )

    quote_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("quote_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    dismissed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: Optional free-text so a pattern of rejections is diagnosable rather
    #: than merely suppressed.
    note: Mapped[LongText | None] = mapped_column(nullable=True)
