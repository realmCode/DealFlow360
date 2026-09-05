"""Table 2/33 — roles."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import RoleCode, enum_col
from app.models.base import Base, LongText, Str128, TimestampMixin, UUIDPrimaryKeyMixin


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """RBAC role. Global (not per-tenant) so permission checks stay uniform."""

    __tablename__ = "roles"
    __table_args__ = (sa.UniqueConstraint("code", name="uq_roles_code"),)

    code: Mapped[RoleCode] = mapped_column(enum_col(RoleCode), nullable=False)
    name: Mapped[Str128] = mapped_column(nullable=False)
    description: Mapped[LongText | None] = mapped_column(nullable=True)
    #: Internal roles may call employee APIs; external roles are portal-only.
    is_internal: Mapped[bool] = mapped_column(nullable=False, default=True)
    #: True when the role may act as an approver on an approval step.
    can_approve: Mapped[bool] = mapped_column(nullable=False, default=False)
