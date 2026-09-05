"""Authentication schemas."""

from __future__ import annotations

import uuid

from pydantic import EmailStr, Field, field_validator

from app.enums import OrganizationKind, RoleCode
from app.schemas.common import ApiModel, ReadModel


class SignupRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=255)
    role: RoleCode = RoleCode.SALES
    #: Join an existing organization…
    organization_id: uuid.UUID | None = None
    #: …or create one. Exactly one of the two must be supplied.
    organization_name: str | None = Field(default=None, max_length=255)
    organization_kind: OrganizationKind = OrganizationKind.SELLER

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if len(v.encode()) > 72:
            raise ValueError("password must be at most 72 bytes")
        if v.isalpha() or v.isdigit():
            raise ValueError("password must mix letters and at least one non-letter")
        return v


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class RefreshRequest(ApiModel):
    refresh_token: str = Field(min_length=1)


class TokenPair(ReadModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class AuthenticatedUser(ReadModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: RoleCode
    organization_id: uuid.UUID
    organization_name: str
    organization_kind: OrganizationKind
    is_internal: bool


class LoginResponse(ReadModel):
    tokens: TokenPair
    user: AuthenticatedUser
