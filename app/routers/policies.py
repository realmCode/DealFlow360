"""Policy read endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.dependencies import DbSession, InternalUser
from app.enums import PolicyType
from app.errors import NotFoundError
from app.models.policy import Policy
from app.schemas.policy import PolicyRead

router = APIRouter(tags=["policies"])


@router.get(
    "/policies",
    response_model=list[PolicyRead],
    summary="List governance policies",
)
async def list_policies(
    user: InternalUser,
    db: DbSession,
    policy_type: PolicyType | None = Query(default=None),
    include_inactive: bool = Query(default=False),
) -> list[PolicyRead]:
    stmt = select(Policy).where(Policy.organization_id == user.organization_id)
    if policy_type is not None:
        stmt = stmt.where(Policy.policy_type == policy_type)
    if not include_inactive:
        stmt = stmt.where(Policy.is_active.is_(True))
    stmt = stmt.order_by(Policy.policy_type, Policy.priority, Policy.code)
    return [PolicyRead.model_validate(p) for p in (await db.execute(stmt)).scalars()]


@router.get(
    "/policies/{policy_id}", response_model=PolicyRead, summary="Get one policy"
)
async def get_policy(
    policy_id: uuid.UUID, user: InternalUser, db: DbSession
) -> PolicyRead:
    policy = await db.get(Policy, policy_id)
    if policy is None or policy.organization_id != user.organization_id:
        raise NotFoundError("Policy not found.")
    return PolicyRead.model_validate(policy)
