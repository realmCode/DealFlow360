"""Sales order endpoints: read, allocate, fulfil."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession, IdempotencyKeyHeader, InternalUser
from app.enums import RoleCode
from app.errors import AuthorizationError, NotFoundError
from app.models.customer_profile import CustomerProfile
from app.models.sales_order import SalesOrder
from app.schemas.inventory import AllocateRequest, AllocationResult, FulfillRequest
from app.schemas.order import (
    AllocationRead,
    FulfillmentRead,
    SalesOrderLineRead,
    SalesOrderRead,
)
from app.services.idempotency import IdempotencyService
from app.services.inventory_service import InventoryService
from app.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


async def _to_read(db, order: SalesOrder) -> SalesOrderRead:  # noqa: ANN001
    from app.models.fulfillment import Fulfillment
    from app.models.warehouse import Warehouse

    lines = await OrderService.lines_for_order(db, order.id)
    allocations = await InventoryService.allocations_for_order(db, order.id)
    fulfillment_rows = (
        await db.execute(
            select(Fulfillment, Warehouse)
            .outerjoin(Warehouse, Warehouse.id == Fulfillment.warehouse_id)
            .where(Fulfillment.sales_order_id == order.id)
            .order_by(Fulfillment.shipment_sequence)
        )
    ).all()
    profile = await db.get(CustomerProfile, order.customer_profile_id)

    return SalesOrderRead(
        id=order.id,
        created_at=order.created_at,
        updated_at=order.updated_at,
        order_number=order.order_number,
        deal_id=order.deal_id,
        quote_id=order.quote_id,
        quote_version_id=order.quote_version_id,
        customer_profile_id=order.customer_profile_id,
        customer_organization_id=order.customer_organization_id,
        customer_name=profile.display_name if profile else None,
        status=order.status,
        currency=order.currency,
        payment_terms=order.payment_terms,
        gross_revenue=order.gross_revenue,
        total_discount=order.total_discount,
        subtotal=order.subtotal,
        tax_amount=order.tax_amount,
        total_amount=order.total_amount,
        total_cost=order.total_cost,
        margin=order.margin,
        margin_pct=order.margin_pct,
        one_time_amount=order.one_time_amount,
        recurring_amount=order.recurring_amount,
        confirmed_by_user_id=order.confirmed_by_user_id,
        confirmed_at=order.confirmed_at,
        fully_allocated=order.fully_allocated,
        has_backorder=order.has_backorder,
        allocated_at=order.allocated_at,
        fulfilled_at=order.fulfilled_at,
        lines=[SalesOrderLineRead.model_validate(line) for line in lines],
        allocations=[
            AllocationRead(
                id=a.id,
                sales_order_line_id=a.sales_order_line_id,
                product_id=a.product_id,
                warehouse_id=a.warehouse_id,
                warehouse_code=w.code if w else None,
                warehouse_name=w.name if w else "Backorder (awaiting restock)",
                quantity=a.quantity,
                status=a.status.value,
                mode=a.mode.value,
                expected_available_at=a.expected_available_at,
                notes=a.notes,
            )
            for a, w in allocations
        ],
        fulfillments=[
            FulfillmentRead(
                id=f.id,
                fulfillment_number=f.fulfillment_number,
                warehouse_id=f.warehouse_id,
                warehouse_name=w.name if w else None,
                shipment_sequence=f.shipment_sequence,
                status=f.status,
                carrier=f.carrier,
                tracking_number=f.tracking_number,
                shipping_cost=f.shipping_cost,
                shipped_at=f.shipped_at,
                delivered_at=f.delivered_at,
            )
            for f, w in fulfillment_rows
        ],
    )


@router.get("", response_model=list[SalesOrderRead], summary="List orders")
async def list_orders(
    user: InternalUser,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[SalesOrderRead]:
    orders = (
        await db.execute(
            select(SalesOrder)
            .where(SalesOrder.organization_id == user.organization_id)
            .order_by(SalesOrder.confirmed_at.desc())
            .limit(limit)
        )
    ).scalars()
    return [await _to_read(db, order) for order in orders]


@router.get("/{order_id}", response_model=SalesOrderRead, summary="Get one order")
async def get_order(
    order_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> SalesOrderRead:
    """Internal users see their org's orders.

    A portal user is refused here on purpose: the full order shape exposes cost
    and margin. Their receipt comes back from the confirm endpoint instead.
    """
    if user.role_code is RoleCode.CUSTOMER:
        raise AuthorizationError(
            "Customer portal users cannot read internal order records. The order "
            "receipt is returned when you confirm the quote.",
            code="PORTAL_USER_FORBIDDEN",
        )
    order = await OrderService.get_order(db, order_id, user.organization_id)
    return await _to_read(db, order)


@router.post(
    "/{order_id}/allocate",
    response_model=AllocationResult,
    summary="Allocate stock across warehouses (atomic, SELECT FOR UPDATE)",
)
async def allocate(
    order_id: uuid.UUID,
    payload: AllocateRequest,
    user: InternalUser,
    db: DbSession,
    idempotency_key: IdempotencyKeyHeader,
) -> AllocationResult:
    if user.role_code not in (RoleCode.OPS, RoleCode.ADMIN, RoleCode.SALES):
        raise AuthorizationError(
            "Only OPS, SALES or ADMIN may allocate inventory.",
            details={"your_role": user.role_code.value},
        )
    order = await OrderService.get_order(db, order_id, user.organization_id)

    record, replay = await IdempotencyService.claim(
        db,
        key=idempotency_key,
        endpoint=f"POST /orders/{order_id}/allocate",
        method="POST",
        user=user,
        payload=payload.model_dump(),
    )
    if replay is not None:
        await db.commit()
        return AllocationResult(**{**replay, "idempotent_replay": True})

    result = await InventoryService.allocate_order(
        db,
        order=order,
        actor=user,
        overrides=payload.overrides,
        allow_partial=payload.allow_partial,
    )
    await IdempotencyService.complete(
        db,
        record,
        status_code=200,
        body=result,
        entity_type="sales_order",
        entity_id=order.id,
    )
    await db.commit()
    return AllocationResult(**result)


@router.post(
    "/{order_id}/fulfill",
    response_model=SalesOrderRead,
    summary="Ship allocated stock — one fulfilment per warehouse",
)
async def fulfill(
    order_id: uuid.UUID,
    payload: FulfillRequest,
    user: InternalUser,
    db: DbSession,
) -> SalesOrderRead:
    if user.role_code not in (RoleCode.OPS, RoleCode.ADMIN):
        raise AuthorizationError(
            "Only OPS or ADMIN may fulfil orders.",
            details={"your_role": user.role_code.value},
        )
    order = await OrderService.get_order(db, order_id, user.organization_id)
    await InventoryService.fulfill_order(
        db,
        order=order,
        actor=user,
        warehouse_id=payload.warehouse_id,
        carrier=payload.carrier,
        tracking_number=payload.tracking_number,
    )
    await db.commit()
    return await _to_read(db, order)


@router.get(
    "/{order_id}/allocations",
    response_model=list[AllocationRead],
    summary="Allocation detail for an order",
)
async def order_allocations(
    order_id: uuid.UUID, user: InternalUser, db: DbSession
) -> list[AllocationRead]:
    order = await OrderService.get_order(db, order_id, user.organization_id)
    rows = await InventoryService.allocations_for_order(db, order.id)
    if not rows and order is None:
        raise NotFoundError("Order not found.")
    return [
        AllocationRead(
            id=a.id,
            sales_order_line_id=a.sales_order_line_id,
            product_id=a.product_id,
            warehouse_id=a.warehouse_id,
            warehouse_code=w.code if w else None,
            warehouse_name=w.name if w else "Backorder (awaiting restock)",
            quantity=a.quantity,
            status=a.status.value,
            mode=a.mode.value,
            expected_available_at=a.expected_available_at,
            notes=a.notes,
        )
        for a, w in rows
    ]
