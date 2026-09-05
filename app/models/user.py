"""Table 3/33 — users."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import RoleCode
from app.models.base import (
    Base,
    OrgOwnedMixin,
    Str32,
    Str255,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.organization import Organization
from app.models.role import Role


class User(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    """A login. Always scoped to exactly one organization."""

    __tablename__ = "users"
    __table_args__ = (
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.Index("ix_users_organization_id_role_id", "organization_id", "role_id"),
    )

    email: Mapped[Str255] = mapped_column(nullable=False)
    hashed_password: Mapped[Str255] = mapped_column(nullable=False)
    full_name: Mapped[Str255] = mapped_column(nullable=False)
    phone: Mapped[Str32 | None] = mapped_column(nullable=True)
    role_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    role: Mapped[Role] = relationship(lazy="joined")
    organization: Mapped[Organization] = relationship(lazy="joined")

    # -- convenience -------------------------------------------------------
    @property
    def role_code(self) -> RoleCode:
        return self.role.code

    @property
    def is_internal(self) -> bool:
        return bool(self.role.is_internal)
