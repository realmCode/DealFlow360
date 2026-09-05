"""Lightweight in-process domain events.

No Kafka, no broker, no extra infrastructure. A domain event is emitted inside
the *same* database transaction as the state change that produced it, so audit
records and attention items can never drift from business state: either both
commit or neither does.

Handlers are plain async callables registered against an ``EventType``.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncSession


class EventType(StrEnum):
    """Canonical business events. Mirrors the audit trail vocabulary."""

    USER_SIGNED_UP = "USER_SIGNED_UP"
    USER_LOGGED_IN = "USER_LOGGED_IN"
    QUOTE_CREATED = "QUOTE_CREATED"
    QUOTE_CALCULATED = "QUOTE_CALCULATED"
    QUOTE_SUBMITTED = "QUOTE_SUBMITTED"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_REVISION_REQUESTED = "APPROVAL_REVISION_REQUESTED"
    APPROVAL_MARKED_STALE = "APPROVAL_MARKED_STALE"
    QUOTE_APPROVED = "QUOTE_APPROVED"
    QUOTE_SENT = "QUOTE_SENT"
    CUSTOMER_COUNTERED = "CUSTOMER_COUNTERED"
    CUSTOMER_COMMENTED = "CUSTOMER_COMMENTED"
    QUOTE_REVISED = "QUOTE_REVISED"
    MATERIAL_CHANGE_DETECTED = "MATERIAL_CHANGE_DETECTED"
    QUOTE_CONFIRMED = "QUOTE_CONFIRMED"
    ORDER_CREATED = "ORDER_CREATED"
    INVENTORY_ALLOCATED = "INVENTORY_ALLOCATED"
    INVENTORY_SHORTAGE = "INVENTORY_SHORTAGE"
    ORDER_FULFILLED = "ORDER_FULFILLED"
    BILLING_SCHEDULED = "BILLING_SCHEDULED"
    ATTENTION_ITEM_CREATED = "ATTENTION_ITEM_CREATED"
    ATTENTION_ITEM_RESOLVED = "ATTENTION_ITEM_RESOLVED"


@dataclass(slots=True)
class DomainEvent:
    event_type: EventType
    organization_id: uuid.UUID | None
    entity_type: str
    entity_id: uuid.UUID | None
    payload: dict[str, Any] = field(default_factory=dict)
    actor_user_id: uuid.UUID | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


EventHandler = Callable[["AsyncSession", DomainEvent], Awaitable[None]]

_handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
_global_handlers: list[EventHandler] = []


def subscribe(event_type: EventType) -> Callable[[EventHandler], EventHandler]:
    """Register a handler for one event type."""

    def _wrap(handler: EventHandler) -> EventHandler:
        if handler not in _handlers[event_type]:
            _handlers[event_type].append(handler)
        return handler

    return _wrap


def subscribe_all(handler: EventHandler) -> EventHandler:
    """Register a handler invoked for every event (used by the audit trail)."""
    if handler not in _global_handlers:
        _global_handlers.append(handler)
    return handler


async def emit(session: "AsyncSession", event: DomainEvent) -> DomainEvent:
    """Dispatch an event to all handlers using the caller's session.

    Handlers run inline (not fire-and-forget) so their writes participate in the
    caller's transaction. Handler failures propagate on purpose: an audit write
    failing must fail the business operation, not be swallowed.
    """
    for handler in _global_handlers:
        await handler(session, event)
    for handler in _handlers[event.event_type]:
        await handler(session, event)
    return event


def registered_handlers() -> dict[str, int]:
    """Introspection helper used by tests and the health endpoint."""
    counts = {k.value: len(v) for k, v in _handlers.items() if v}
    counts["*"] = len(_global_handlers)
    return counts


def _reset_handlers_for_tests() -> None:  # pragma: no cover - test utility
    _handlers.clear()
    _global_handlers.clear()
