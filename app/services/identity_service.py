"""IdentityService — organizations, roles, users, signup and login."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import settings
from app.db import discard_pending
from app.enums import EXTERNAL_ROLES, INTERNAL_ROLES, OrganizationKind, RoleCode
from app.errors import (
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
)
from app.events import EventType
from app.middleware.auth import (
    create_access_token,
    create_refresh_token,
    hash_password,
    subject_from_token,
    verify_password,
)
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.services.audit_service import AuditService

ROLE_DEFINITIONS: tuple[tuple[RoleCode, str, str, bool, bool], ...] = (
    (
        RoleCode.SALES,
        "Sales Representative",
        "Builds deals and quotes. Cannot approve anything, including own quotes.",
        True,
        False,
    ),
    (
        RoleCode.MANAGER,
        "Sales Manager",
        "First-line approver for discount ceiling breaches.",
        True,
        True,
    ),
    (
        RoleCode.FINANCE,
        "Finance Approver",
        "Approves margin violations and deals above discount signing authority.",
        True,
        True,
    ),
    (
        RoleCode.OPS,
        "Operations",
        "Runs inventory allocation and fulfilment.",
        True,
        False,
    ),
    (
        RoleCode.CUSTOMER,
        "Customer Portal User",
        "External buyer. Portal endpoints only; never sees cost or margin.",
        False,
        False,
    ),
    (
        RoleCode.ADMIN,
        "Administrator",
        "Configures catalog, warehouses and policies; may act on any approval step.",
        True,
        True,
    ),
)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:60] or "org"


class IdentityService:
    # --------------------------------------------------------------- roles
    @staticmethod
    async def ensure_roles(session: AsyncSession) -> dict[RoleCode, Role]:
        """Idempotently create the six RBAC roles."""
        existing = {
            role.code: role
            for role in (await session.execute(select(Role))).scalars()
        }
        created = False
        for code, name, description, is_internal, can_approve in ROLE_DEFINITIONS:
            if code in existing:
                continue
            role = Role(
                code=code,
                name=name,
                description=description,
                is_internal=is_internal,
                can_approve=can_approve,
            )
            session.add(role)
            existing[code] = role
            created = True
        if created:
            await session.flush()
        return existing

    @staticmethod
    async def get_role(session: AsyncSession, code: RoleCode) -> Role:
        role = (
            await session.execute(select(Role).where(Role.code == code))
        ).scalar_one_or_none()
        if role is None:
            roles = await IdentityService.ensure_roles(session)
            role = roles[code]
        return role

    # -------------------------------------------------------- organizations
    @staticmethod
    async def ensure_organization(
        session: AsyncSession,
        *,
        name: str,
        kind: OrganizationKind,
        slug: str | None = None,
        domain: str | None = None,
        currency: str = "USD",
    ) -> Organization:
        target_slug = slug or slugify(name)
        existing = (
            await session.execute(
                select(Organization).where(Organization.slug == target_slug)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        org = Organization(
            name=name,
            slug=target_slug,
            kind=kind,
            domain=domain,
            currency=currency,
        )
        session.add(org)
        await session.flush()
        return org

    # --------------------------------------------------------------- users
    @staticmethod
    def _validate_role_org_pairing(role_code: RoleCode, org: Organization) -> None:
        """A portal role in a seller org (or vice versa) would break isolation."""
        if role_code in EXTERNAL_ROLES and org.kind is not OrganizationKind.CUSTOMER:
            raise BusinessRuleError(
                "A CUSTOMER user must belong to an organization of kind CUSTOMER.",
                code="ROLE_ORG_MISMATCH",
                details={"role": role_code.value, "organization_kind": org.kind.value},
            )
        if role_code in INTERNAL_ROLES and org.kind is not OrganizationKind.SELLER:
            raise BusinessRuleError(
                f"A {role_code.value} user must belong to an organization of kind "
                f"SELLER.",
                code="ROLE_ORG_MISMATCH",
                details={"role": role_code.value, "organization_kind": org.kind.value},
            )

    @classmethod
    async def create_user(
        cls,
        session: AsyncSession,
        *,
        email: str,
        password: str,
        full_name: str,
        role_code: RoleCode,
        organization: Organization,
    ) -> User:
        normalized = email.strip().lower()
        cls._validate_role_org_pairing(role_code, organization)

        duplicate = (
            await session.execute(select(User.id).where(User.email == normalized))
        ).scalar_one_or_none()
        if duplicate is not None:
            raise ConflictError(
                "An account with that email address already exists.",
                code="EMAIL_ALREADY_REGISTERED",
                details={"email": normalized},
            )

        role = await cls.get_role(session, role_code)
        user = User(
            organization_id=organization.id,
            email=normalized,
            hashed_password=hash_password(password),
            full_name=full_name,
            role_id=role.id,
            is_active=True,
        )
        try:
        # ``session.add`` must happen *inside* the SAVEPOINT: an object made
        # pending before the savepoint begins survives its rollback, so the
        # next flush retries the same failing INSERT and poisons the outer
        # transaction with PendingRollbackError.
            async with session.begin_nested():
                session.add(user)
                await session.flush()
        except IntegrityError as exc:
            discard_pending(session, user)
            raise ConflictError(
                "An account with that email address already exists.",
                code="EMAIL_ALREADY_REGISTERED",
                details={"email": normalized},
            ) from exc

        # Re-read so `user.role`/`user.organization` are populated.
        return await cls.load_user(session, user.id)

    @staticmethod
    async def load_user(session: AsyncSession, user_id: uuid.UUID) -> User:
        result = await session.execute(
            select(User)
            .options(joinedload(User.role), joinedload(User.organization))
            .where(User.id == user_id)
        )
        user = result.unique().scalar_one_or_none()
        if user is None:
            raise NotFoundError("User not found.")
        return user

    @staticmethod
    async def by_email(session: AsyncSession, email: str) -> User | None:
        result = await session.execute(
            select(User)
            .options(joinedload(User.role), joinedload(User.organization))
            .where(User.email == email.strip().lower())
        )
        return result.unique().scalar_one_or_none()

    # -------------------------------------------------------------- signup
    @classmethod
    async def signup(
        cls, session: AsyncSession, payload, *, ip_address: str | None = None
    ) -> User:
        await cls.ensure_roles(session)

        if payload.organization_id is not None:
            org = await session.get(Organization, payload.organization_id)
            if org is None or not org.is_active:
                raise NotFoundError(
                    "Organization not found.",
                    details={"organization_id": str(payload.organization_id)},
                )
        elif payload.organization_name:
            org = await cls.ensure_organization(
                session,
                name=payload.organization_name,
                kind=payload.organization_kind,
            )
        else:
            raise BusinessRuleError(
                "Supply either organization_id (to join an existing organization) or "
                "organization_name (to create one).",
                code="ORGANIZATION_REQUIRED",
            )

        user = await cls.create_user(
            session,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            role_code=payload.role,
            organization=org,
        )
        await AuditService.emit(
            session,
            EventType.USER_SIGNED_UP,
            organization_id=org.id,
            entity_type="user",
            entity_id=user.id,
            actor=user,
            payload={
                "role": payload.role.value,
                "organization": org.name,
                "organization_kind": org.kind.value,
            },
            ip_address=ip_address,
        )
        return user

    # --------------------------------------------------------------- login
    @classmethod
    async def authenticate(
        cls, session: AsyncSession, *, email: str, password: str
    ) -> User:
        user = await cls.by_email(session, email)
        # Same message for unknown email and wrong password: no user enumeration.
        if user is None or not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password.")
        if not user.is_active:
            raise AuthenticationError(
                "User account is disabled.", code="USER_DISABLED"
            )
        if not user.organization.is_active:
            raise AuthenticationError(
                "Organization is disabled.", code="ORGANIZATION_DISABLED"
            )
        user.last_login_at = datetime.now(UTC)
        await session.flush()
        return user

    @staticmethod
    def issue_tokens(user: User) -> dict[str, object]:
        return {
            "access_token": create_access_token(
                user.id,
                organization_id=user.organization_id,
                role=user.role_code.value,
                email=user.email,
            ),
            "refresh_token": create_refresh_token(user.id),
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
        }

    @classmethod
    async def refresh(cls, session: AsyncSession, refresh_token: str) -> User:
        user_id = subject_from_token(refresh_token, expected_type="refresh")
        user = await cls.load_user(session, user_id)
        if not user.is_active:
            raise AuthenticationError("User account is disabled.", code="USER_DISABLED")
        return user

    @staticmethod
    def to_authenticated(user: User) -> dict[str, object]:
        return {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role_code,
            "organization_id": user.organization_id,
            "organization_name": user.organization.name,
            "organization_kind": user.organization.kind,
            "is_internal": user.is_internal,
        }

    @staticmethod
    async def list_users(
        session: AsyncSession, organization_id: uuid.UUID
    ) -> list[User]:
        result = await session.execute(
            select(User)
            .options(joinedload(User.role), joinedload(User.organization))
            .where(User.organization_id == organization_id)
            .order_by(User.email)
        )
        return list(result.unique().scalars())

    @staticmethod
    async def count_users(session: AsyncSession) -> int:
        return int(
            (await session.execute(select(func.count()).select_from(User))).scalar_one()
        )
