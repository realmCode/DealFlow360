"""Table 4/33 — contacts."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    OrgOwnedMixin,
    Str32,
    Str128,
    Str255,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Contact(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """A person at a customer organization. May or may not have a login.

    ``organization_id`` is the seller that owns the CRM record;
    ``customer_organization_id`` is the org the person actually belongs to.
    """

    __tablename__ = "contacts"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id", "email", name="uq_contacts_organization_id_email"
        ),
        sa.Index("ix_contacts_customer_organization_id", "customer_organization_id"),
    )

    customer_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    first_name: Mapped[Str128] = mapped_column(nullable=False)
    last_name: Mapped[Str128 | None] = mapped_column(nullable=True)
    email: Mapped[Str255] = mapped_column(nullable=False)
    phone: Mapped[Str32 | None] = mapped_column(nullable=True)
    title: Mapped[Str128 | None] = mapped_column(nullable=True)
    is_primary: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    @property
    def display_name(self) -> str:
        return " ".join(filter(None, [self.first_name, self.last_name]))
