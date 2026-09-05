"""Sales team management.

PDF A7.4 requires reports filterable by "Sales Team / Rep". `deals.owner_user_id`
already provided Rep; Team had no entity, so half the filter had nothing to
filter on.

Membership is many-to-many on purpose: a rep can belong to a regional team and
a vertical team at once, and forcing a single team FK on `users` would make one
of those unrepresentable.
"""

from __future__ import annotations

import uuid
from typing import Any, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import INTERNAL_ROLES
from app.errors import BusinessRuleError, ConflictError, NotFoundError
from app.models.sales_team import SalesTeam, SalesTeamMember
from app.models.user import User


class SalesTeamService:
    @staticmethod
    async def get(
        session: AsyncSession, team_id: uuid.UUID, organization_id: uuid.UUID
    ) -> SalesTeam:
        team = await session.get(SalesTeam, team_id)
        if team is None or team.organization_id != organization_id:
            raise NotFoundError("Sales team not found.")
        return team

    @staticmethod
    async def _validate_members(
        session: AsyncSession,
        organization_id: uuid.UUID,
        user_ids: Sequence[uuid.UUID],
    ) -> list[User]:
        if not user_ids:
            return []
        users = list(
            (
                await session.execute(
                    select(User).where(
                        User.id.in_(user_ids),
                        User.organization_id == organization_id,
                    )
                )
            ).scalars()
        )
        found = {u.id for u in users}
        missing = [str(uid) for uid in user_ids if uid not in found]
        if missing:
            raise NotFoundError(
                "One or more users are not in your organization.",
                details={"missing_user_ids": missing},
            )
        # A portal user on a sales team would corrupt every rep-scoped
        # aggregate, so reject rather than silently include them.
        external = [u.email for u in users if u.role_code not in INTERNAL_ROLES]
        if external:
            raise BusinessRuleError(
                "Customer portal users cannot be members of a sales team.",
                code="EXTERNAL_USER_NOT_ELIGIBLE",
                details={"emails": external},
            )
        return users

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        code: str,
        name: str,
        description: str | None,
        manager_user_id: uuid.UUID | None,
        region: str | None,
        member_user_ids: Sequence[uuid.UUID] = (),
    ) -> SalesTeam:
        duplicate = (
            await session.execute(
                select(SalesTeam.id).where(
                    SalesTeam.organization_id == organization_id,
                    SalesTeam.code == code,
                )
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise ConflictError(
                f"Sales team code {code} already exists.",
                code="SALES_TEAM_CODE_EXISTS",
                details={"code": code},
            )

        if manager_user_id is not None:
            await cls._validate_members(session, organization_id, [manager_user_id])

        team = SalesTeam(
            organization_id=organization_id,
            code=code,
            name=name,
            description=description,
            manager_user_id=manager_user_id,
            region=region,
        )
        session.add(team)
        await session.flush()

        if member_user_ids:
            await cls.add_members(
                session,
                team=team,
                user_ids=member_user_ids,
                organization_id=organization_id,
            )
        return team

    @classmethod
    async def add_members(
        cls,
        session: AsyncSession,
        *,
        team: SalesTeam,
        user_ids: Sequence[uuid.UUID],
        organization_id: uuid.UUID,
    ) -> int:
        await cls._validate_members(session, organization_id, user_ids)
        existing = set(
            (
                await session.execute(
                    select(SalesTeamMember.user_id).where(
                        SalesTeamMember.sales_team_id == team.id
                    )
                )
            ).scalars()
        )
        added = 0
        for user_id in user_ids:
            if user_id in existing:
                continue
            session.add(
                SalesTeamMember(
                    organization_id=organization_id,
                    sales_team_id=team.id,
                    user_id=user_id,
                )
            )
            added += 1
        await session.flush()
        return added

    @staticmethod
    async def remove_member(
        session: AsyncSession, *, team: SalesTeam, user_id: uuid.UUID
    ) -> None:
        result = await session.execute(
            delete(SalesTeamMember).where(
                SalesTeamMember.sales_team_id == team.id,
                SalesTeamMember.user_id == user_id,
            )
        )
        if result.rowcount == 0:
            raise NotFoundError(
                "That user is not a member of this team.",
                details={"user_id": str(user_id)},
            )

    @staticmethod
    async def members(
        session: AsyncSession, team_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        rows = (
            await session.execute(
                select(User)
                .join(SalesTeamMember, SalesTeamMember.user_id == User.id)
                .where(SalesTeamMember.sales_team_id == team_id)
                .order_by(User.full_name)
            )
        ).scalars()
        return [
            {
                "user_id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role_code.value,
            }
            for u in rows
        ]

    @classmethod
    async def to_read(
        cls, session: AsyncSession, team: SalesTeam
    ) -> dict[str, Any]:
        manager_name: str | None = None
        if team.manager_user_id is not None:
            manager = await session.get(User, team.manager_user_id)
            manager_name = manager.full_name if manager else None
        return {
            "id": team.id,
            "created_at": team.created_at,
            "updated_at": team.updated_at,
            "code": team.code,
            "name": team.name,
            "description": team.description,
            "manager_user_id": team.manager_user_id,
            "manager_name": manager_name,
            "region": team.region,
            "is_active": team.is_active,
            "members": await cls.members(session, team.id),
        }

    @staticmethod
    async def list_teams(
        session: AsyncSession,
        organization_id: uuid.UUID,
        *,
        include_inactive: bool = False,
    ) -> list[SalesTeam]:
        stmt = select(SalesTeam).where(
            SalesTeam.organization_id == organization_id
        )
        if not include_inactive:
            stmt = stmt.where(SalesTeam.is_active.is_(True))
        return list((await session.execute(stmt.order_by(SalesTeam.name))).scalars())
