"""Reusable FastAPI dependencies: database, current user, RBAC.

Authorization is enforced **here and in the services**, never by hiding a
button in the frontend. Every internal route declares the roles it accepts.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db import get_db
from app.enums import INTERNAL_ROLES, RoleCode
from app.errors import AuthenticationError, AuthorizationError
from app.middleware.auth import subject_from_token
from app.models.user import User

# auto_error=False so a missing header produces our JSON envelope, not FastAPI's.
_bearer = HTTPBearer(auto_error=False, description="JWT access token")

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: DbSession,
) -> User:
    """Resolve and validate the caller.

    The user row is re-read on every request so deactivation and role changes
    apply immediately rather than when the token happens to expire.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer token.")

    user_id = subject_from_token(credentials.credentials, expected_type="access")

    result = await db.execute(
        select(User)
        .options(joinedload(User.role), joinedload(User.organization))
        .where(User.id == user_id)
    )
    user = result.unique().scalar_one_or_none()
    if user is None:
        raise AuthenticationError("Token subject no longer exists.")
    if not user.is_active:
        raise AuthenticationError("User account is disabled.", code="USER_DISABLED")
    if not user.organization.is_active:
        raise AuthenticationError(
            "Organization is disabled.", code="ORGANIZATION_DISABLED"
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(
    *allowed: RoleCode,
) -> Callable[..., Coroutine[Any, Any, User]]:
    """Dependency factory restricting a route to specific roles."""
    allowed_set = set(allowed)

    async def _dependency(user: CurrentUser) -> User:
        if user.role_code not in allowed_set:
            raise AuthorizationError(
                f"Role {user.role_code.value} cannot perform this action.",
                details={
                    "your_role": user.role_code.value,
                    "allowed_roles": sorted(r.value for r in allowed_set),
                },
            )
        return user

    return _dependency


async def require_internal_user(user: CurrentUser) -> User:
    """Any employee role. Explicitly blocks customer portal users."""
    if user.role_code not in INTERNAL_ROLES:
        raise AuthorizationError(
            "Customer portal users cannot access internal endpoints.",
            code="PORTAL_USER_FORBIDDEN",
            details={"your_role": user.role_code.value, "use_instead": "/portal/*"},
        )
    return user


async def require_customer_user(user: CurrentUser) -> User:
    """Portal-only routes. Employees are blocked so redaction is never bypassed."""
    if user.role_code != RoleCode.CUSTOMER:
        raise AuthorizationError(
            "Only customer portal users may use the portal endpoints.",
            code="INTERNAL_USER_FORBIDDEN",
            details={"your_role": user.role_code.value},
        )
    return user


InternalUser = Annotated[User, Depends(require_internal_user)]
CustomerUser = Annotated[User, Depends(require_customer_user)]
AdminUser = Annotated[User, Depends(require_role(RoleCode.ADMIN))]

#: Roles that may author commercial documents.
#:
#: MANAGER is included deliberately: sales managers own deals in practice. The
#: safeguard against them waving their own quote through is the self-approval
#: check in :class:`ApprovalService`, not the absence of authoring rights —
#: authorship, not role, is what disqualifies an approver.
SalesUser = Annotated[
    User, Depends(require_role(RoleCode.SALES, RoleCode.MANAGER, RoleCode.ADMIN))
]
ApproverUser = Annotated[
    User, Depends(require_role(RoleCode.MANAGER, RoleCode.FINANCE, RoleCode.ADMIN))
]
OpsUser = Annotated[User, Depends(require_role(RoleCode.OPS, RoleCode.ADMIN))]


async def get_idempotency_key(
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description=(
                "Client-generated key that makes a retried request safe. "
                "Required on order confirmation and inventory allocation."
            ),
        ),
    ] = None,
) -> str | None:
    return idempotency_key


IdempotencyKeyHeader = Annotated[str | None, Depends(get_idempotency_key)]


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()
