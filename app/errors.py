"""Consistent API error taxonomy.

Every error surfaces the same JSON envelope so the future frontend can branch on
a stable machine-readable `code` instead of parsing prose:

    {
      "error": {
        "code": "STALE_APPROVAL",
        "message": "Quote cannot be confirmed: approval is stale.",
        "details": {...}
      }
    }
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


class DealFlowError(HTTPException):
    """Base class for all DealFlow360 business/API errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "BAD_REQUEST"
    default_message: str = "Request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.code = code or self.code
        self.details = details or {}
        self.message = message or self.default_message
        super().__init__(
            status_code=status_code or self.status_code,
            detail={
                "error": {
                    "code": self.code,
                    "message": self.message,
                    "details": self.details,
                }
            },
        )


# ---------------------------------------------------------------- 400 / 422
class ValidationError(DealFlowError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "VALIDATION_ERROR"
    default_message = "Payload failed validation."


class BusinessRuleError(DealFlowError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "BUSINESS_RULE_VIOLATION"
    default_message = "Operation violates a business rule."


# --------------------------------------------------------------------- 401
class AuthenticationError(DealFlowError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "AUTHENTICATION_FAILED"
    default_message = "Authentication required or credentials invalid."

    def __init__(self, message: str | None = None, **kw: Any) -> None:
        super().__init__(message, **kw)
        self.headers = {"WWW-Authenticate": "Bearer"}


# --------------------------------------------------------------------- 403
class AuthorizationError(DealFlowError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"
    default_message = "You are not permitted to perform this action."


class TenantIsolationError(AuthorizationError):
    code = "TENANT_ISOLATION"
    default_message = "Resource does not belong to your organization."


# --------------------------------------------------------------------- 404
class NotFoundError(DealFlowError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"
    default_message = "Resource not found."


# --------------------------------------------------------------------- 409
class ConflictError(DealFlowError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    default_message = "Request conflicts with the current resource state."


class ImmutableVersionError(ConflictError):
    code = "IMMUTABLE_VERSION"
    default_message = (
        "This quote version is immutable. Create a revision to change it."
    )


class StaleApprovalError(ConflictError):
    code = "STALE_APPROVAL"
    default_message = (
        "A prior approval was invalidated by a material change and must be renewed."
    )


class ApprovalRequiredError(ConflictError):
    code = "APPROVAL_REQUIRED"
    default_message = "The quote version is not approved."


class DuplicateOperationError(ConflictError):
    code = "DUPLICATE_OPERATION"
    default_message = "This operation has already been performed."


class IdempotencyConflictError(ConflictError):
    code = "IDEMPOTENCY_KEY_REUSED"
    default_message = (
        "Idempotency key was already used with a different request payload."
    )


class InsufficientInventoryError(ConflictError):
    code = "INSUFFICIENT_INVENTORY"
    default_message = "Not enough stock available to satisfy the request."
