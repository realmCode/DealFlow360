"""Control Tower, attention items, deal health and the audit timeline."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.dependencies import DbSession, InternalUser
from app.enums import AttentionItemStatus, AttentionItemType, Severity
from app.errors import NotFoundError
from app.models.attention_item import AttentionItem
from app.models.audit_event import AuditEvent
from app.models.deal import Deal
from app.schemas.dashboard import (
    AttentionItemRead,
    AttentionItemResolve,
    AuditEventRead,
    ControlTowerRead,
    DealHealthList,
    DealHealthRead,
)
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
    response_model=list[AttentionItemRead],
    summary="Attention items — each states why, impact, owner and next action",
)
async def attention_items(
    user: InternalUser,
    db: DbSession,
    severity: Severity | None = Query(default=None),
    type: AttentionItemType | None = Query(default=None),
    include_resolved: bool = Query(default=False),
) -> list[AttentionItemRead]:
    items = await DashboardService.open_items(
        db,
        user.organization_id,
        severity=severity,
        item_type=type,
        include_resolved=include_resolved,
    )
    return [AttentionItemRead.model_validate(i) for i in items]


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
    item = await db.get(AttentionItem, item_id)
    if item is None or item.organization_id != user.organization_id:
        raise NotFoundError("Attention item not found.")
    item.status = AttentionItemStatus.RESOLVED
    item.resolved_at = datetime.now(UTC)
    item.resolved_by_user_id = user.id
    item.resolution_note = payload.resolution_note
    await db.flush()
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
    response_model=list[AuditEventRead],
    summary="Append-only audit timeline",
)
async def audit_events(
    user: InternalUser,
    db: DbSession,
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[AuditEventRead]:
    stmt = select(AuditEvent).where(AuditEvent.organization_id == user.organization_id)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    stmt = stmt.order_by(AuditEvent.sequence).limit(limit)
    return [
        AuditEventRead.model_validate(e) for e in (await db.execute(stmt)).scalars()
    ]


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
