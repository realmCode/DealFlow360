"""Table 1/33 — organizations."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import OrganizationKind, enum_col
from app.models.base import Base, Str64, Str255, TimestampMixin, UUIDPrimaryKeyMixin


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant. Either the seller (TechSupply) or a buyer (Acme)."""

    __tablename__ = "organizations"
    __table_args__ = (
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
        sa.Index("ix_organizations_kind", "kind"),
    )

    name: Mapped[Str255] = mapped_column(nullable=False)
    slug: Mapped[Str64] = mapped_column(nullable=False)
    kind: Mapped[OrganizationKind] = mapped_column(
        enum_col(OrganizationKind), nullable=False, default=OrganizationKind.SELLER
    )
    domain: Mapped[Str255 | None] = mapped_column(nullable=True)
    country: Mapped[Str64 | None] = mapped_column(nullable=True)
    currency: Mapped[str] = mapped_column(sa.String(3), nullable=False, default="USD")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    @property
    def is_seller(self) -> bool:
        return self.kind == OrganizationKind.SELLER
