"""Tenant (organization) scoping helpers.

Two rules, applied everywhere:

1. **Internal users** may only touch rows whose ``organization_id`` equals
   their own organization. Cross-org reads raise 404 — not 403 — so an
   attacker cannot use the error code to probe which ids exist elsewhere.
2. **Customer portal users** never match on ``organization_id`` at all. Their
   access is granted through ``customer_profiles.customer_organization_id``,
   which is checked explicitly by the portal service.
"""

from __future__ import annotations

import uuid
from typing import Any, TypeVar

from sqlalchemy import Select

from app.errors import NotFoundError
from app.models.user import User

T = TypeVar("T")


def scope_to_org(stmt: Select[Any], model: Any, organization_id: uuid.UUID) -> Select[Any]:
    """Append the tenant predicate to a select statement."""
    return stmt.where(model.organization_id == organization_id)


def assert_same_org(
    entity: Any,
    user: User,
    *,
    entity_name: str = "Resource",
    entity_id: uuid.UUID | None = None,
) -> None:
    """Guard a loaded row against cross-tenant access.

    Raises ``NotFoundError`` (never 403) so response codes cannot be used to
    enumerate identifiers belonging to other organizations.
    """
    if entity is None:
        raise NotFoundError(
            f"{entity_name} not found.",
            details={"entity": entity_name, "id": str(entity_id) if entity_id else None},
        )
    entity_org = getattr(entity, "organization_id", None)
    if entity_org is not None and entity_org != user.organization_id:
        raise NotFoundError(
            f"{entity_name} not found.",
            details={"entity": entity_name, "reason": "outside your organization"},
        )


def require_entity(
    entity: T | None, *, entity_name: str = "Resource", entity_id: Any = None
) -> T:
    if entity is None:
        raise NotFoundError(
            f"{entity_name} not found.",
            details={"entity": entity_name, "id": str(entity_id) if entity_id else None},
        )
    return entity
