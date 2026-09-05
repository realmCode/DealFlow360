"""Password hashing and JWT token handling."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.errors import AuthenticationError

_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.effective_bcrypt_rounds,
)

TokenType = Literal["access", "refresh"]


def hash_password(plain: str) -> str:
    # bcrypt silently truncates at 72 bytes; reject rather than hash a prefix.
    if len(plain.encode()) > 72:
        raise AuthenticationError("Password must be at most 72 bytes.")
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(plain, hashed)
    except ValueError:
        return False


def _create_token(
    subject: uuid.UUID,
    token_type: TokenType,
    expires_delta: timedelta,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    if extra:
        claims.update(extra)
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(
    user_id: uuid.UUID,
    *,
    organization_id: uuid.UUID,
    role: str,
    email: str,
) -> str:
    """Short-lived token.

    Role and org are embedded for observability only — every request still
    re-reads the user row, so revoking a user or changing their role takes
    effect immediately instead of at token expiry.
    """
    return _create_token(
        user_id,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        {"org": str(organization_id), "role": role, "email": email},
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    return _create_token(
        user_id, "refresh", timedelta(days=settings.refresh_token_expire_days)
    )


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as exc:
        raise AuthenticationError("Token is invalid or expired.") from exc

    if payload.get("type") != expected_type:
        raise AuthenticationError(
            f"Expected a {expected_type} token, got {payload.get('type')!r}.",
            code="WRONG_TOKEN_TYPE",
        )
    if not payload.get("sub"):
        raise AuthenticationError("Token is missing a subject.")
    return payload


def subject_from_token(token: str, *, expected_type: TokenType) -> uuid.UUID:
    payload = decode_token(token, expected_type=expected_type)
    try:
        return uuid.UUID(str(payload["sub"]))
    except (ValueError, KeyError) as exc:
        raise AuthenticationError("Token subject is not a valid user id.") from exc
