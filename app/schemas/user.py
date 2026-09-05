"""User and organization schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field

from app.enums import OrganizationKind, RoleCode
from app.schemas.common import ApiModel, ReadModel, TimestampedRead


class OrganizationRead(TimestampedRead):
    name: str
    slug: str
    kind: OrganizationKind
    currency: str
    is_active: bool


class OrganizationCreate(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=64)
    kind: OrganizationKind = OrganizationKind.SELLER
    domain: str | None = Field(default=None, max_length=255)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class RoleRead(TimestampedRead):
    code: RoleCode
    name: str
    is_internal: bool
    can_approve: bool


class UserRead(TimestampedRead):
    email: str
    full_name: str
    role: RoleCode
    organization_id: uuid.UUID
    organization_name: str
    is_active: bool
    is_internal: bool
    last_login_at: datetime | None = None


class UserCreate(ApiModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=255)
    role: RoleCode
    organization_id: uuid.UUID | None = None


class UserSummary(ReadModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: RoleCode
