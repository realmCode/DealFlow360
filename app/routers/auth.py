"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.dependencies import DbSession, client_ip
from app.events import EventType
from app.schemas.auth import (
    AuthenticatedUser,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    SignupRequest,
    TokenPair,
)
from app.services.audit_service import AuditService
from app.services.identity_service import IdentityService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=LoginResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a user (and optionally its organization)",
)
async def signup(
    payload: SignupRequest, db: DbSession, request: Request
) -> LoginResponse:
    user = await IdentityService.signup(db, payload, ip_address=client_ip(request))
    await db.commit()
    return LoginResponse(
        tokens=TokenPair(**IdentityService.issue_tokens(user)),
        user=AuthenticatedUser(**IdentityService.to_authenticated(user)),
    )


@router.post("/login", response_model=LoginResponse, summary="Exchange credentials for tokens")
async def login(
    payload: LoginRequest, db: DbSession, request: Request
) -> LoginResponse:
    user = await IdentityService.authenticate(
        db, email=payload.email, password=payload.password
    )
    await AuditService.emit(
        db,
        EventType.USER_LOGGED_IN,
        organization_id=user.organization_id,
        entity_type="user",
        entity_id=user.id,
        actor=user,
        payload={"role": user.role_code.value},
        ip_address=client_ip(request),
    )
    await db.commit()
    return LoginResponse(
        tokens=TokenPair(**IdentityService.issue_tokens(user)),
        user=AuthenticatedUser(**IdentityService.to_authenticated(user)),
    )


@router.post(
    "/refresh", response_model=TokenPair, summary="Rotate an access token"
)
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    user = await IdentityService.refresh(db, payload.refresh_token)
    return TokenPair(**IdentityService.issue_tokens(user))
