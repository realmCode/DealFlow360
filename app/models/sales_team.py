"""Tables 35-36 — sales_teams, sales_team_members.

PDF A7.4 requires reports filterable by "Sales Team / Rep". `deals.owner_user_id`
already gives Rep; there was no entity for Team, so that half of the filter had
no subject to filter on.

Membership is a separate table rather than a column on `users` because a rep can
legitimately belong to more than one team (regional plus vertical, for example),
and squeezing that into a single FK would force a false choice.
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
    Str64,
    Str255,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class SalesTeam(UUIDPrimaryKeyMixin, OrgOwnedMixin, TimestampMixin, Base):
    __tablename__ = "sales_teams"
    __table_args__ = (
        sa.UniqueConstraint(
            "organization_id", "code", name="uq_sales_teams_organization_id_code"
        ),
        sa.Index("ix_sales_teams_organization_id_is_active", "organization_id", "is_active"),
    )

    code: Mapped[Str64] = mapped_column(nullable=False)
    name: Mapped[Str255] = mapped_column(nullable=False)
    description: Mapped[LongText | None] = mapped_column(nullable=True)
    #: The manager accountable for the team's number. SET NULL rather than
    #: RESTRICT so deactivating a manager does not block the team record.
    manager_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    region: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=sa.true()
    )


class SalesTeamMember(UUIDPrimaryKeyMixin, OrgOwnedMixin, CreatedAtMixin, Base):
    """Append-only membership record."""

    __tablename__ = "sales_team_members"
    __table_args__ = (
        sa.UniqueConstraint(
            "sales_team_id", "user_id", name="uq_sales_team_members_sales_team_id_user_id"
        ),
        sa.Index("ix_sales_team_members_user_id", "user_id"),
    )

    sales_team_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("sales_teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
