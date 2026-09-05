"""Control Tower, attention items, deal health and the audit timeline."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.dependencies import DbSession, InternalUser
from app.enums import AttentionItemStatus, AttentionItemType, RoleCode, Severity
from app.errors import AuthorizationError, ConflictError, NotFoundError
from app.events import EventType
from app.models.attention_item import AttentionItem
from app.models.audit_event import AuditEvent
from app.models.deal import Deal
from app.models.user import User
from app.schemas.common import Page
from app.schemas.query import Pagination
from app.schemas.dashboard import (
    AttentionItemAcknowledge,
    AttentionItemEscalate,
    AttentionItemNudge,
    AttentionItemRead,
    AttentionItemResolve,
    AuditEventRead,
    ControlTowerRead,
    DealHealthList,
    DealHealthRead,
    NudgeResponse,
)
from app.services.audit_service import AuditService
from app.services.dashboard_service import DashboardService

router = APIRouter(tags=["dashboard"])


@router.get(
    "/dashboard/control-tower",
    response_model=ControlTowerRead,
    summary="Severity-sorted action queue for your organization",
)
async def control_tower(user: InternalUser, db: DbSession) -> ControlTowerRead:
    return ControlTowerRead.model_validate(
        await DashboardService.control_tower(db, user)
    )


@router.get(
    "/dashboard/attention-items",
    response_model=Page[AttentionItemRead],
    summary="Attention items — each states why, impact, owner and next action",
)
async def attention_items(
    user: InternalUser,
    db: DbSession,
    page: Pagination,
    severity: Severity | None = Query(default=None),
    type: AttentionItemType | None = Query(default=None),
    include_resolved: bool = Query(default=False),
    owner_role: RoleCode | None = Query(
        default=None, description="Filter to items owned by one role."
    ),
    mine: bool = Query(
        default=False, description="Only items owned by your role or assigned to you."
    ),
) -> Page[AttentionItemRead]:
    items = await DashboardService.open_items(
        db,
        user.organization_id,
        severity=severity,
        item_type=type,
        include_resolved=include_resolved,
    )
    if owner_role is not None:
        items = [i for i in items if i.owner_role == owner_role]
    if mine:
        items = [
            i
            for i in items
            if i.owner_role == user.role_code or i.owner_user_id == user.id
        ]

    total = len(items)
    window = items[page.offset : page.offset + page.limit]
    return Page[AttentionItemRead](
        items=[AttentionItemRead.model_validate(i) for i in window],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


async def _owned_item(
    db, item_id: uuid.UUID, user: User, *, action: str
) -> AttentionItem:
    """Load an attention item and enforce ownership.

    Ownership was previously recorded but not enforced, so any employee could
    clear a CRITICAL governance alert — including the rep whose own quote
    caused it. The underlying block still held (``assert_confirmable``
    re-checks staleness independently), but the manager's early-warning queue
    could be silently emptied by the person it was warning about.
    """
    item = await db.get(AttentionItem, item_id)
    if item is None or item.organization_id != user.organization_id:
        raise NotFoundError("Attention item not found.")

    permitted = (
        user.role_code is RoleCode.ADMIN
        or user.role_code == item.owner_role
        or (item.owner_user_id is not None and item.owner_user_id == user.id)
    )
    if not permitted:
        raise AuthorizationError(
            f"Only {item.owner_role.value} or ADMIN may {action} this item.",
            code="NOT_ITEM_OWNER",
            details={
                "owner_role": item.owner_role.value,
                "your_role": user.role_code.value,
                "action": action,
            },
        )
    return item


@router.post(
    "/dashboard/attention-items/{item_id}/resolve",
    response_model=AttentionItemRead,
    summary="Manually resolve an attention item",
)
async def resolve_attention_item(
    item_id: uuid.UUID,
    payload: AttentionItemResolve,
    user: InternalUser,
    db: DbSession,
) -> AttentionItemRead:
    item = await _owned_item(db, item_id, user, action="resolve")
    item.status = AttentionItemStatus.RESOLVED
    item.resolved_at = datetime.now(UTC)
    item.resolved_by_user_id = user.id
    item.resolution_note = payload.resolution_note
    await db.flush()
    await AuditService.emit(
        db,
        EventType.ATTENTION_ITEM_RESOLVED,
        organization_id=user.organization_id,
        entity_type="attention_item",
        entity_id=item.id,
        actor=user,
        payload={
            "type": item.type.value,
            "title": item.title,
            "note": payload.resolution_note,
            "resolved_count": 1,
            "source_type": item.source_type,
            "source_id": str(item.source_id),
        },
    )
    await db.commit()
    return AttentionItemRead.model_validate(item)


@router.post(
    "/dashboard/attention-items/{item_id}/acknowledge",
    response_model=AttentionItemRead,
    summary="Acknowledge an item — seen and being worked, not yet resolved",
)
async def acknowledge_attention_item(
    item_id: uuid.UUID,
    payload: AttentionItemAcknowledge,
    user: InternalUser,
    db: DbSession,
) -> AttentionItemRead:
    """Makes ``AttentionItemStatus.ACKNOWLEDGED`` reachable.

    Without it the queue had only two states, so an owner had to either leave
    an item looking untouched or resolve it prematurely to clear it.
    """
    item = await _owned_item(db, item_id, user, action="acknowledge")
    if item.status is AttentionItemStatus.RESOLVED:
        raise ConflictError(
            "This item is already resolved.",
            code="ITEM_ALREADY_RESOLVED",
            details={"item_id": str(item.id)},
        )
    item.status = AttentionItemStatus.ACKNOWLEDGED
    item.acknowledged_at = datetime.now(UTC)
    item.acknowledged_by_user_id = user.id
    if payload.note:
        item.escalation_note = payload.note
    await db.flush()
    await AuditService.emit(
        db,
        EventType.ATTENTION_ITEM_ACKNOWLEDGED,
        organization_id=user.organization_id,
        entity_type="attention_item",
        entity_id=item.id,
        actor=user,
        payload={"type": item.type.value, "title": item.title, "note": payload.note},
    )
    await db.commit()
    return AttentionItemRead.model_validate(item)


@router.post(
    "/dashboard/attention-items/{item_id}/nudge",
    response_model=NudgeResponse,
    summary="Nudge the owner of an item (PDF B9)",
)
async def nudge_attention_item(
    item_id: uuid.UUID,
    payload: AttentionItemNudge,
    user: InternalUser,
    db: DbSession,
) -> NudgeResponse:
    """PDF B9 — "An automated nudge ... can be triggered from an alert".

    Anyone internal may nudge: the point is to prod the owner, so restricting
    it to the owner would make it useless. The count is recorded so a
    repeatedly-ignored alert becomes visible as a problem in its own right.
    """
    item = await db.get(AttentionItem, item_id)
    if item is None or item.organization_id != user.organization_id:
        raise NotFoundError("Attention item not found.")
    if item.status is AttentionItemStatus.RESOLVED:
        raise ConflictError(
            "This item is already resolved and does not need a nudge.",
            code="ITEM_ALREADY_RESOLVED",
            details={"item_id": str(item.id)},
        )

    item.nudge_count = int(item.nudge_count or 0) + 1
    item.last_nudged_at = datetime.now(UTC)
    item.last_nudged_by_user_id = user.id
    await db.flush()
    await AuditService.emit(
        db,
        EventType.ATTENTION_ITEM_NUDGED,
        organization_id=user.organization_id,
        entity_type="attention_item",
        entity_id=item.id,
        actor=user,
        payload={
            "type": item.type.value,
            "title": item.title,
            "owner_role": item.owner_role.value,
            "nudge_count": item.nudge_count,
            "note": payload.note,
        },
    )
    await db.commit()
    return NudgeResponse(
        item=AttentionItemRead.model_validate(item),
        message=(
            f"{item.owner_role.value} has been nudged about "
            f"'{item.title}' ({item.nudge_count} time(s) so far)."
        ),
        notified_role=item.owner_role,
        nudge_count=item.nudge_count,
    )


@router.post(
    "/dashboard/attention-items/{item_id}/escalate",
    response_model=AttentionItemRead,
    summary="Escalate an item — raise severity and optionally reassign (PDF B9)",
)
async def escalate_attention_item(
    item_id: uuid.UUID,
    payload: AttentionItemEscalate,
    user: InternalUser,
    db: DbSession,
) -> AttentionItemRead:
    """PDF B9 — "... or escalation action can be triggered from an alert"."""
    item = await db.get(AttentionItem, item_id)
    if item is None or item.organization_id != user.organization_id:
        raise NotFoundError("Attention item not found.")
    if item.status is AttentionItemStatus.RESOLVED:
        raise ConflictError(
            "A resolved item cannot be escalated.",
            code="ITEM_ALREADY_RESOLVED",
            details={"item_id": str(item.id)},
        )

    ladder = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
    current = ladder.index(item.severity)
    previous_severity = item.severity
    if current < len(ladder) - 1:
        item.severity = ladder[current + 1]

    previous_owner = item.owner_role
    if payload.owner_role is not None:
        item.owner_role = payload.owner_role
        # The previous owner-specific assignment no longer applies once the
        # owning role changes.
        item.owner_user_id = None

    item.escalated_at = datetime.now(UTC)
    item.escalated_by_user_id = user.id
    item.escalation_note = payload.note
    await db.flush()
    await AuditService.emit(
        db,
        EventType.ATTENTION_ITEM_ESCALATED,
        organization_id=user.organization_id,
        entity_type="attention_item",
        entity_id=item.id,
        actor=user,
        payload={
            "type": item.type.value,
            "title": item.title,
            "previous_severity": previous_severity.value,
            "new_severity": item.severity.value,
            "previous_owner_role": previous_owner.value,
            "new_owner_role": item.owner_role.value,
            "note": payload.note,
        },
    )
    await db.commit()
    return AttentionItemRead.model_validate(item)


@router.get(
    "/dashboard/deal-health",
    response_model=DealHealthList,
    summary="Deterministic deal health scores, worst first",
)
async def deal_health(user: InternalUser, db: DbSession) -> DealHealthList:
    return DealHealthList.model_validate(
        await DashboardService.deal_health_list(db, user.organization_id)
    )


@router.get(
    "/dashboard/deal-health/{deal_id}",
    response_model=DealHealthRead,
    summary="Health score for one deal, with every deduction explained",
)
async def deal_health_one(
    deal_id: uuid.UUID, user: InternalUser, db: DbSession
) -> DealHealthRead:
    deal = await db.get(Deal, deal_id)
    if deal is None or deal.organization_id != user.organization_id:
        raise NotFoundError("Deal not found.")
    return DealHealthRead.model_validate(
        await DashboardService.deal_health(db, user.organization_id, deal)
    )


@router.get(
    "/audit/events",
    response_model=Page[AuditEventRead],
    summary="Append-only audit timeline (paginated, filterable)",
)
async def audit_events(
    user: InternalUser,
    db: DbSession,
    page: Pagination,
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    actor_user_id: uuid.UUID | None = Query(default=None),
    newest_first: bool = Query(
        default=False,
        description="Sequence order by default, which is the story order.",
    ),
) -> Page[AuditEventRead]:
    stmt = select(AuditEvent).where(AuditEvent.organization_id == user.organization_id)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if actor_user_id:
        stmt = stmt.where(AuditEvent.actor_user_id == actor_user_id)

    total = (
        await db.execute(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
    ).scalar_one()

    stmt = stmt.order_by(
        AuditEvent.sequence.desc() if newest_first else AuditEvent.sequence
    )
    rows = (
        await db.execute(stmt.limit(page.limit).offset(page.offset))
    ).scalars()
    return Page[AuditEventRead](
        items=[AuditEventRead.model_validate(e) for e in rows],
        total=int(total),
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/audit/quotes/{quote_id}/timeline",
    response_model=list[AuditEventRead],
    summary="Full timeline for a quote: every actor, every decision",
)
async def quote_timeline(
    quote_id: uuid.UUID,
    user: InternalUser,
    db: DbSession,
) -> list[AuditEventRead]:
    from app.models.approval_request import ApprovalRequest
    from app.models.quote_version import QuoteVersion
    from app.models.sales_order import SalesOrder
    from app.services.quote_service import QuoteService

    quote = await QuoteService.get_quote(db, quote_id, user.organization_id)

    ids: set[uuid.UUID] = {quote.id}
    for version in await QuoteService.versions_for_quote(db, quote.id):
        ids.add(version.id)
    for request in (
        await db.execute(
            select(ApprovalRequest.id).where(ApprovalRequest.quote_id == quote.id)
        )
    ).scalars():
        ids.add(request)
    for order in (
        await db.execute(select(SalesOrder.id).where(SalesOrder.quote_id == quote.id))
    ).scalars():
        ids.add(order)
    for message_id in (
        await db.execute(
            select(AuditEvent.entity_id).where(
                AuditEvent.organization_id == user.organization_id,
                AuditEvent.entity_type == "negotiation_message",
                AuditEvent.payload["quote_id"].as_string() == str(quote.id),
            )
        )
    ).scalars():
        if message_id:
            ids.add(message_id)
    _ = QuoteVersion  # documentation of the tables walked above

    rows = (
        await db.execute(
            select(AuditEvent)
            .where(
                AuditEvent.organization_id == user.organization_id,
                AuditEvent.entity_id.in_(ids),
            )
            .order_by(AuditEvent.sequence)
        )
    ).scalars()
    return [AuditEventRead.model_validate(e) for e in rows]
