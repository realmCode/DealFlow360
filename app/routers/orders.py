"""Sales order endpoints: read, allocate, fulfil."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.dependencies import (
    AllocatingUser,
    CurrentUser,
    DbSession,
    IdempotencyKeyHeader,
    InternalUser,
    OpsUser,
    SalesUser,
)
from app.enums import RoleCode
from app.errors import AuthorizationError, NotFoundError
from app.models.customer_profile import CustomerProfile
from app.models.sales_order import SalesOrder
from app.schemas.common import Page
from app.schemas.inventory import AllocateRequest, AllocationResult, FulfillRequest
from app.schemas.order import (
    AllocationRead,
    DeliveryConfirmRequest,
    FulfillmentRead,
    OrderCancelRequest,
    PromiseUpdate,
    SalesOrderLineRead,
    SalesOrderRead,
    SalesOrderSummary,
)
from app.schemas.query import Pagination, Sorting
from app.services.idempotency import IdempotencyService
from app.services.inventory_service import InventoryService
from app.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])

ORDER_SORTABLE = {
    "confirmed_at": SalesOrder.confirmed_at,
    "created_at": SalesOrder.created_at,
    "order_number": SalesOrder.order_number,
    "total_amount": SalesOrder.total_amount,
    "status": SalesOrder.status,
}


def _is_late(order: SalesOrder) -> bool:
    """PDF B9.3 — promised date passed with the order still unfulfilled."""
    promised = order.promised_delivery_date
    return bool(
        promised
        and order.fulfilled_at is None
        and promised < datetime.now(UTC).date()
    )


def _days_late(order: SalesOrder) -> int:
    if not _is_late(order):
        return 0
    return (datetime.now(UTC).date() - order.promised_delivery_date).days


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
        promised_delivery_date=order.promised_delivery_date,
        is_delivery_late=_is_late(order),
        days_late=_days_late(order),
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


@router.get(
    "",
    response_model=Page[SalesOrderSummary],
    summary="List orders (paginated summary; use the detail route for lines)",
)
async def list_orders(
    user: InternalUser,
    db: DbSession,
    page: Pagination,
    sort: Sorting,
    status_: str | None = Query(default=None, alias="status"),
    customer_profile_id: uuid.UUID | None = Query(default=None),
    has_backorder: bool | None = Query(default=None),
    overdue_delivery: bool | None = Query(
        default=None,
        description="Only orders whose promised delivery date has passed unfulfilled.",
    ),
) -> Page[SalesOrderSummary]:
    """Returns a summary rather than the full order graph.

    The previous version loaded every line, allocation and fulfilment for every
    order in the list — a per-order fan-out of four queries. A list screen
    needs totals and status; the detail route supplies the rest.
    """
    stmt = (
        select(SalesOrder, CustomerProfile.display_name)
        .join(
            CustomerProfile, CustomerProfile.id == SalesOrder.customer_profile_id
        )
        .where(SalesOrder.organization_id == user.organization_id)
    )
    if status_ is not None:
        stmt = stmt.where(SalesOrder.status == status_)
    if customer_profile_id is not None:
        stmt = stmt.where(SalesOrder.customer_profile_id == customer_profile_id)
    if has_backorder is not None:
        stmt = stmt.where(SalesOrder.has_backorder.is_(has_backorder))
    if overdue_delivery:
        today = datetime.now(UTC).date()
        stmt = stmt.where(
            SalesOrder.promised_delivery_date.is_not(None),
            SalesOrder.promised_delivery_date < today,
            SalesOrder.fulfilled_at.is_(None),
        )

    total = (
        await db.execute(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
    ).scalar_one()

    column, descending = sort.resolve(ORDER_SORTABLE, default="confirmed_at")
    stmt = stmt.order_by(column.desc() if descending else column.asc())
    stmt = stmt.limit(page.limit).offset(page.offset)

    today = datetime.now(UTC).date()
    items: list[SalesOrderSummary] = []
    for order, customer_name in (await db.execute(stmt)).all():
        promised = order.promised_delivery_date
        late = bool(
            promised and promised < today and order.fulfilled_at is None
        )
        items.append(
            SalesOrderSummary(
                id=order.id,
                order_number=order.order_number,
                deal_id=order.deal_id,
                quote_id=order.quote_id,
                customer_profile_id=order.customer_profile_id,
                customer_name=customer_name,
                status=order.status,
                currency=order.currency,
                payment_terms=order.payment_terms,
                subtotal=order.subtotal,
                tax_amount=order.tax_amount,
                total_amount=order.total_amount,
                margin=order.margin,
                margin_pct=order.margin_pct,
                one_time_amount=order.one_time_amount,
                recurring_amount=order.recurring_amount,
                fully_allocated=order.fully_allocated,
                has_backorder=order.has_backorder,
                promised_delivery_date=promised,
                is_delivery_late=late,
                days_late=(today - promised).days if late else 0,
                confirmed_at=order.confirmed_at,
                allocated_at=order.allocated_at,
                fulfilled_at=order.fulfilled_at,
            )
        )

    return Page[SalesOrderSummary](
        items=items, total=int(total), limit=page.limit, offset=page.offset
    )


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
    user: AllocatingUser,
    db: DbSession,
    idempotency_key: IdempotencyKeyHeader,
) -> AllocationResult:
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
    user: OpsUser,
    db: DbSession,
) -> SalesOrderRead:
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


@router.patch(
    "/{order_id}/promise",
    response_model=SalesOrderRead,
    summary="Set or revise the promised delivery date",
)
async def set_delivery_promise(
    order_id: uuid.UUID,
    payload: PromiseUpdate,
    user: SalesUser,
    db: DbSession,
) -> SalesOrderRead:
    """PDF B9.3 needs a commitment to measure slippage against; without a
    recorded promise there is nothing for a slippage indicator to compare."""
    order = await OrderService.get_order(db, order_id, user.organization_id)
    order.promised_delivery_date = payload.promised_delivery_date
    await db.flush()
    await db.commit()
    return await _to_read(db, order)


@router.post(
    "/{order_id}/fulfillments/{fulfillment_id}/deliver",
    response_model=SalesOrderRead,
    summary="Confirm a shipment was delivered",
)
async def confirm_delivery(
    order_id: uuid.UUID,
    fulfillment_id: uuid.UUID,
    payload: DeliveryConfirmRequest,
    user: OpsUser,
    db: DbSession,
) -> SalesOrderRead:
    """Makes ``FulfillmentStatus.DELIVERED`` reachable.

    Slippage needs both a promise and a completion signal; previously a
    shipment could be marked SHIPPED and never confirmed, so a delivered order
    was indistinguishable from one still in transit.
    """
    order = await OrderService.get_order(db, order_id, user.organization_id)
    await InventoryService.confirm_delivery(
        db,
        order=order,
        fulfillment_id=fulfillment_id,
        actor=user,
        delivered_at=payload.delivered_at,
        note=payload.note,
    )
    await db.commit()
    return await _to_read(db, order)


@router.post(
    "/{order_id}/cancel",
    response_model=SalesOrderRead,
    summary="Cancel an order and release its reserved stock",
)
async def cancel_order(
    order_id: uuid.UUID,
    payload: OrderCancelRequest,
    user: OpsUser,
    db: DbSession,
) -> SalesOrderRead:
    """``SalesOrderStatus.CANCELLED`` was read but never set, so an order
    created in error could not be voided and its reservations stayed locked
    against stock forever."""
    order = await OrderService.get_order(db, order_id, user.organization_id)
    await InventoryService.cancel_order(
        db, order=order, actor=user, reason=payload.reason
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
