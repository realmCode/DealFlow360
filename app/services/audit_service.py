"""Audit trail and attention-item creation, driven by domain events.

The audit log is written by a **global** event subscriber, so any service that
emits an event gets an audit record for free and cannot forget one. Because
handlers run on the caller's session, the audit row and the business change
commit or roll back together.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import discard_pending
from app.enums import (
    AttentionItemStatus,
    AttentionItemType,
    RoleCode,
    SEVERITY_RANK,
    Severity,
)
from app.events import DomainEvent, EventType, emit, subscribe_all
from app.models.attention_item import AttentionItem
from app.models.audit_event import AuditEvent
from app.models.user import User


def jsonable(value: Any) -> Any:
    """Make an arbitrary value safe for a JSONB column.

    Decimals become strings (never floats — a float round-trip would corrupt
    the audit record of a monetary decision).
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    return value


@subscribe_all
async def _write_audit_event(session: AsyncSession, event: DomainEvent) -> None:
    """Global handler: every emitted event becomes an append-only audit row."""
    actor_email: str | None = event.payload.get("_actor_email")
    actor_role: RoleCode | None = None
    raw_role = event.payload.get("_actor_role")
    if raw_role:
        actor_role = RoleCode(raw_role)

    payload = {k: v for k, v in event.payload.items() if not k.startswith("_")}

    session.add(
        AuditEvent(
            organization_id=event.organization_id,
            event_type=event.event_type.value,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            actor_user_id=event.actor_user_id,
            actor_role=actor_role,
            actor_email=actor_email,
            payload=jsonable(payload),
            ip_address=event.payload.get("_ip_address"),
            occurred_at=event.occurred_at,
        )
    )


class AuditService:
    """Thin façade over the event bus used by every other service."""

    @staticmethod
    async def emit(
        session: AsyncSession,
        event_type: EventType,
        *,
        organization_id: uuid.UUID | None,
        entity_type: str,
        entity_id: uuid.UUID | None,
        actor: User | None = None,
        payload: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> DomainEvent:
        data: dict[str, Any] = dict(payload or {})
        if actor is not None:
            data["_actor_email"] = actor.email
            data["_actor_role"] = actor.role_code.value
        if ip_address:
            data["_ip_address"] = ip_address

        event = DomainEvent(
            event_type=event_type,
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=data,
            actor_user_id=actor.id if actor else None,
        )
        await emit(session, event)
        # Flush so ordering (audit_events.sequence) reflects emission order even
        # when several events fire inside one transaction.
        await session.flush()
        return event

    @staticmethod
    async def list_for_entity(
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> list[AuditEvent]:
        stmt = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
        if entity_type:
            stmt = stmt.where(AuditEvent.entity_type == entity_type)
        if entity_id:
            stmt = stmt.where(AuditEvent.entity_id == entity_id)
        stmt = stmt.order_by(AuditEvent.sequence).limit(limit)
        return list((await session.execute(stmt)).scalars())


class AttentionService:
    """Creates and resolves Control Tower items.

    Items are idempotent per (source, type): re-running the Decision Fabric on
    the same quote refreshes the existing item instead of spamming the queue.
    """

    @staticmethod
    async def upsert(
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        source_type: str,
        source_id: uuid.UUID,
        item_type: AttentionItemType,
        severity: Severity,
        title: str,
        reason: str,
        impact: str,
        owner_role: RoleCode,
        recommended_action: str,
        owner_user_id: uuid.UUID | None = None,
        deal_id: uuid.UUID | None = None,
        quote_id: uuid.UUID | None = None,
        detail: dict[str, Any] | None = None,
        actor: User | None = None,
    ) -> AttentionItem:
        existing = (
            await session.execute(
                select(AttentionItem).where(
                    AttentionItem.organization_id == organization_id,
                    AttentionItem.source_type == source_type,
                    AttentionItem.source_id == source_id,
                    AttentionItem.type == item_type,
                    AttentionItem.status != AttentionItemStatus.RESOLVED,
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.severity = severity
            existing.title = title
            existing.reason = reason
            existing.impact = impact
            existing.owner_role = owner_role
            existing.owner_user_id = owner_user_id
            existing.recommended_action = recommended_action
            existing.detail = jsonable(detail or {})
            existing.status = AttentionItemStatus.OPEN
            await session.flush()
            return existing

        item = AttentionItem(
            organization_id=organization_id,
            source_type=source_type,
            source_id=source_id,
            type=item_type,
            severity=severity,
            title=title,
            reason=reason,
            impact=impact,
            owner_role=owner_role,
            owner_user_id=owner_user_id,
            recommended_action=recommended_action,
            status=AttentionItemStatus.OPEN,
            deal_id=deal_id,
            quote_id=quote_id,
            detail=jsonable(detail or {}),
        )
        try:
        # ``session.add`` must happen *inside* the SAVEPOINT: an object made
        # pending before the savepoint begins survives its rollback, so the
        # next flush retries the same failing INSERT and poisons the outer
        # transaction with PendingRollbackError.
            async with session.begin_nested():
                session.add(item)
                await session.flush()
        except IntegrityError:
            # Concurrent writer won the partial unique index; adopt their row.
            discard_pending(session, item)
            winner = (
                await session.execute(
                    select(AttentionItem).where(
                        AttentionItem.organization_id == organization_id,
                        AttentionItem.source_type == source_type,
                        AttentionItem.source_id == source_id,
                        AttentionItem.type == item_type,
                        AttentionItem.status != AttentionItemStatus.RESOLVED,
                    )
                )
            ).scalar_one()
            return winner

        await AuditService.emit(
            session,
            EventType.ATTENTION_ITEM_CREATED,
            organization_id=organization_id,
            entity_type="attention_item",
            entity_id=item.id,
            actor=actor,
            payload={
                "type": item_type.value,
                "severity": severity.value,
                "title": title,
                "owner_role": owner_role.value,
                "source_type": source_type,
                "source_id": str(source_id),
            },
        )
        return item

    @staticmethod
    async def resolve(
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        source_type: str,
        source_id: uuid.UUID,
        item_type: AttentionItemType | None = None,
        note: str | None = None,
        actor: User | None = None,
    ) -> int:
        """Close every live item for a source. Returns how many were closed."""
        stmt = select(AttentionItem).where(
            AttentionItem.organization_id == organization_id,
            AttentionItem.source_type == source_type,
            AttentionItem.source_id == source_id,
            AttentionItem.status != AttentionItemStatus.RESOLVED,
        )
        if item_type is not None:
            stmt = stmt.where(AttentionItem.type == item_type)

        items = list((await session.execute(stmt)).scalars())
        now = datetime.now(UTC)
        for item in items:
            item.status = AttentionItemStatus.RESOLVED
            item.resolved_at = now
            item.resolution_note = note
            item.resolved_by_user_id = actor.id if actor else None
        if items:
            await session.flush()
            await AuditService.emit(
                session,
                EventType.ATTENTION_ITEM_RESOLVED,
                organization_id=organization_id,
                entity_type="attention_item",
                entity_id=items[0].id,
                actor=actor,
                payload={
                    "resolved_count": len(items),
                    "source_type": source_type,
                    "source_id": str(source_id),
                    "types": [i.type.value for i in items],
                    "note": note,
                },
            )
        return len(items)

    @staticmethod
    def sort_key(item: AttentionItem) -> tuple[int, float]:
        """Severity desc, then oldest first — the order an operator should work."""
        return (-SEVERITY_RANK[item.severity], item.created_at.timestamp())
