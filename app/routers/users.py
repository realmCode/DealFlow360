"""User endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.dependencies import AdminUser, CurrentUser, DbSession
from app.errors import NotFoundError
from app.models.organization import Organization
from app.schemas.user import UserCreate, UserRead
from app.services.identity_service import IdentityService

router = APIRouter(tags=["users"])


def _to_read(user) -> UserRead:  # noqa: ANN001
    return UserRead(
        id=user.id,
        created_at=user.created_at,
        updated_at=user.updated_at,
        email=user.email,
        full_name=user.full_name,
        role=user.role_code,
        organization_id=user.organization_id,
        organization_name=user.organization.name,
        is_active=user.is_active,
        is_internal=user.is_internal,
        last_login_at=user.last_login_at,
    )


@router.get("/users/me", response_model=UserRead, summary="The authenticated user")
async def me(user: CurrentUser) -> UserRead:
    return _to_read(user)


@router.get(
    "/users",
    response_model=list[UserRead],
    summary="List users in your organization (admin)",
)
async def list_users(admin: AdminUser, db: DbSession) -> list[UserRead]:
    users = await IdentityService.list_users(db, admin.organization_id)
    return [_to_read(u) for u in users]


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user in your organization (admin)",
)
async def create_user(
    payload: UserCreate, admin: AdminUser, db: DbSession
) -> UserRead:
    org_id = payload.organization_id or admin.organization_id
    organization = await db.get(Organization, org_id)
    if organization is None:
        raise NotFoundError("Organization not found.")

    user = await IdentityService.create_user(
        db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role_code=payload.role,
        organization=organization,
    )
    await db.commit()
    return _to_read(user)
