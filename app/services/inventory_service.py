"""InventoryService — atomic multi-warehouse allocation.

Concurrency
-----------
Allocation takes a ``SELECT ... FOR UPDATE`` over every inventory row for the
product before deciding anything, so two orders racing for the same stock
serialise instead of both reading the same "available" figure. Rows are locked
in ``inventory.id`` order and order lines are processed in ``product_id`` order,
which gives every transaction the same lock ordering and removes the deadlock
window.

Belt and braces: ``inventory`` also carries a CHECK constraint
(``quantity_reserved <= quantity_on_hand``). Even if this service had a bug,
PostgreSQL would refuse to over-allocate.

Allocation strategy (generic — nothing about 60/40 is hardcoded)
---------------------------------------------------------------
1. If any single warehouse can cover the whole line, use it — one shipment is
   cheaper than two. Among those that can, pick the lowest ``priority``, then
   the lowest shipping cost, then the largest stock, then the code.
2. Otherwise take the largest available stock first, which minimises the
   number of shipments needed to fill the line.
3. Whatever cannot be sourced becomes a ``BACKORDERED`` allocation with no
   warehouse, carrying the earliest expected restock date.

With Main Warehouse=60 and East Depot=40, an order for 100 laptops falls to
rule 2 and naturally yields 60 + 40. Change the stock and the split changes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    AllocationMode,
    AllocationStatus,
    AttentionItemType,
    BillingScheduleStatus,
    FulfillmentStatus,
    RoleCode,
    SalesOrderStatus,
    Severity,
)
from app.errors import (
    BusinessRuleError,
    ConflictError,
    InsufficientInventoryError,
    NotFoundError,
)
from app.events import EventType
from app.models.billing_schedule import BillingSchedule
from app.models.fulfillment import Fulfillment
from app.models.inventory import Inventory
from app.models.inventory_allocation import InventoryAllocation
from app.models.product import Product
from app.models.sales_order import SalesOrder
from app.models.sales_order_line import SalesOrderLine
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.audit_service import AttentionService, AuditService
from app.services.commercial_engine import ZERO, format_quantity, money

QTY_ZERO = Decimal("0")


@dataclass(slots=True)
class Split:
    warehouse_id: uuid.UUID | None
    warehouse_code: str
    warehouse_name: str
    quantity: Decimal
    backorder: bool = False


@dataclass(slots=True)
class LinePlan:
    line: SalesOrderLine
    product: Product
    requested: Decimal
    splits: list[Split] = field(default_factory=list)

    @property
    def allocated(self) -> Decimal:
        return sum((s.quantity for s in self.splits if not s.backorder), QTY_ZERO)

    @property
    def backordered(self) -> Decimal:
        return sum((s.quantity for s in self.splits if s.backorder), QTY_ZERO)


class InventoryService:
    # -------------------------------------------------------------- setup
    @staticmethod
    async def upsert_stock(
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
        quantity_on_hand: Decimal,
        quantity_inbound: Decimal = QTY_ZERO,
        reorder_point: Decimal = QTY_ZERO,
        expected_restock_at: datetime | None = None,
    ) -> Inventory:
        warehouse = await session.get(Warehouse, warehouse_id)
        if warehouse is None or warehouse.organization_id != organization_id:
            raise NotFoundError("Warehouse not found.")
        product = await session.get(Product, product_id)
        if product is None or product.organization_id != organization_id:
            raise NotFoundError("Product not found.")

        row = (
            await session.execute(
                select(Inventory)
                .where(
                    Inventory.warehouse_id == warehouse_id,
                    Inventory.product_id == product_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

        if row is None:
            row = Inventory(
                organization_id=organization_id,
                warehouse_id=warehouse_id,
                product_id=product_id,
                quantity_on_hand=Decimal(quantity_on_hand),
                quantity_inbound=Decimal(quantity_inbound),
                reorder_point=Decimal(reorder_point),
                expected_restock_at=expected_restock_at,
            )
            session.add(row)
        else:
            if Decimal(quantity_on_hand) < Decimal(row.quantity_reserved):
                raise ConflictError(
                    f"Cannot set stock to {quantity_on_hand}: "
                    f"{row.quantity_reserved} units are already reserved.",
                    code="STOCK_BELOW_RESERVED",
                    details={"quantity_reserved": str(row.quantity_reserved)},
                )
            row.quantity_on_hand = Decimal(quantity_on_hand)
            row.quantity_inbound = Decimal(quantity_inbound)
            row.reorder_point = Decimal(reorder_point)
            row.expected_restock_at = expected_restock_at
        await session.flush()
        return row

    @staticmethod
    async def adjust_stock(
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
        delta: Decimal,
        reason: str,
        actor: User | None = None,
    ) -> Inventory:
        """Apply a signed stock movement. Positive = receipt, negative = shrinkage."""
        row = (
            await session.execute(
                select(Inventory)
                .where(
                    Inventory.organization_id == organization_id,
                    Inventory.warehouse_id == warehouse_id,
                    Inventory.product_id == product_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("No stock record for that warehouse/product pair.")

        new_on_hand = Decimal(row.quantity_on_hand) + Decimal(delta)
        if new_on_hand < ZERO:
            raise ConflictError(
                f"Adjustment would take stock negative "
                f"({row.quantity_on_hand} {delta:+}).",
                code="STOCK_NEGATIVE",
            )
        if new_on_hand < Decimal(row.quantity_reserved):
            raise ConflictError(
                f"Adjustment would leave {row.quantity_reserved} reserved units "
                f"unbacked by stock.",
                code="STOCK_BELOW_RESERVED",
            )
        row.quantity_on_hand = new_on_hand
        await session.flush()
        return row

    # ------------------------------------------------------------ read side
    @staticmethod
    async def allocations_for_order(
        session: AsyncSession, order_id: uuid.UUID
    ) -> list[tuple[InventoryAllocation, Warehouse | None]]:
        rows = (
            await session.execute(
                select(InventoryAllocation, Warehouse)
                .outerjoin(Warehouse, Warehouse.id == InventoryAllocation.warehouse_id)
                .where(InventoryAllocation.sales_order_id == order_id)
                .order_by(InventoryAllocation.created_at)
            )
        ).all()
        return [(a, w) for a, w in rows]

    # ----------------------------------------------------------- allocate
    @classmethod
    async def allocate_order(
        cls,
        session: AsyncSession,
        *,
        order: SalesOrder,
        actor: User,
        overrides: Sequence[Any] = (),
        allow_partial: bool = True,
    ) -> dict[str, Any]:
        """Reserve stock for every outstanding stock-tracked line, atomically."""
        if order.status is SalesOrderStatus.CANCELLED:
            raise ConflictError(
                "A cancelled order cannot be allocated.", code="ORDER_CANCELLED"
            )

        lines = list(
            (
                await session.execute(
                    select(SalesOrderLine)
                    .where(SalesOrderLine.sales_order_id == order.id)
                    # Deterministic lock ordering across concurrent allocations.
                    .order_by(SalesOrderLine.product_id, SalesOrderLine.line_number)
                )
            ).scalars()
        )

        override_map: dict[uuid.UUID, list[Any]] = {}
        for entry in overrides:
            override_map.setdefault(entry.sales_order_line_id, []).append(entry)

        known_line_ids = {line.id for line in lines}
        for line_id in override_map:
            if line_id not in known_line_ids:
                raise NotFoundError(
                    "Override references a line that is not on this order.",
                    details={"sales_order_line_id": str(line_id)},
                )

        plans: list[LinePlan] = []
        for line in lines:
            product = await session.get(Product, line.product_id)
            assert product is not None
            outstanding = Decimal(line.quantity) - Decimal(line.quantity_allocated)

            if not line.is_stock_tracked:
                # Services and subscriptions have nothing to draw down; they are
                # considered fully "allocated" the moment the order exists.
                if outstanding > ZERO:
                    line.quantity_allocated = Decimal(line.quantity)
                plans.append(
                    LinePlan(line=line, product=product, requested=outstanding)
                )
                continue

            if outstanding <= ZERO:
                plans.append(LinePlan(line=line, product=product, requested=ZERO))
                continue

            plan = await cls._plan_line(
                session,
                order=order,
                line=line,
                product=product,
                outstanding=outstanding,
                overrides=override_map.get(line.id, []),
            )
            plans.append(plan)

            if not allow_partial and plan.backordered > ZERO:
                raise InsufficientInventoryError(
                    f"Only {format_quantity(plan.allocated)} of "
                    f"{format_quantity(outstanding)} units of "
                    f"'{product.name}' can be sourced, and partial allocation was "
                    f"not permitted.",
                    details={
                        "product": product.name,
                        "requested": str(outstanding),
                        "available": str(plan.allocated),
                    },
                )

        # ------------------------------------------------- persist the plan
        result_lines: list[dict[str, Any]] = []
        shipment_warehouses: set[uuid.UUID] = set()

        for plan in plans:
            for split in plan.splits:
                inventory_id: uuid.UUID | None = None
                if not split.backorder and split.warehouse_id is not None:
                    inv = (
                        await session.execute(
                            select(Inventory).where(
                                Inventory.warehouse_id == split.warehouse_id,
                                Inventory.product_id == plan.line.product_id,
                            )
                        )
                    ).scalar_one()
                    inventory_id = inv.id
                    shipment_warehouses.add(split.warehouse_id)

                session.add(
                    InventoryAllocation(
                        organization_id=order.organization_id,
                        sales_order_id=order.id,
                        sales_order_line_id=plan.line.id,
                        product_id=plan.line.product_id,
                        warehouse_id=split.warehouse_id,
                        inventory_id=inventory_id,
                        quantity=split.quantity,
                        status=(
                            AllocationStatus.BACKORDERED
                            if split.backorder
                            else AllocationStatus.ALLOCATED
                        ),
                        mode=(
                            AllocationMode.MANUAL_OVERRIDE
                            if plan.line.id in override_map
                            else AllocationMode.AUTOMATIC
                        ),
                        allocated_by_user_id=actor.id,
                        expected_available_at=(
                            await cls._earliest_restock(
                                session, order.organization_id, plan.line.product_id
                            )
                            if split.backorder
                            else None
                        ),
                        notes=(
                            "Awaiting restock — no warehouse currently holds this "
                            "stock."
                            if split.backorder
                            else None
                        ),
                    )
                )

            plan.line.quantity_allocated = Decimal(plan.line.quantity_allocated) + plan.allocated
            plan.line.quantity_backordered = (
                Decimal(plan.line.quantity_backordered) + plan.backordered
            )

            if plan.splits:
                result_lines.append(
                    {
                        "sales_order_line_id": plan.line.id,
                        "product_id": plan.line.product_id,
                        "product_name": plan.product.name,
                        "quantity_requested": plan.requested,
                        "quantity_allocated": plan.allocated,
                        "quantity_backordered": plan.backordered,
                        "splits": [
                            {
                                "warehouse_code": s.warehouse_code,
                                "warehouse_name": s.warehouse_name,
                                "quantity": str(s.quantity),
                                "status": (
                                    "BACKORDERED" if s.backorder else "ALLOCATED"
                                ),
                            }
                            for s in plan.splits
                        ],
                        "explanation": cls._explain_plan(plan),
                    }
                )

        await session.flush()
        return await cls._finalise(
            session,
            order=order,
            actor=actor,
            plans=plans,
            result_lines=result_lines,
            shipment_count=len(shipment_warehouses),
        )

    @classmethod
    async def _plan_line(
        cls,
        session: AsyncSession,
        *,
        order: SalesOrder,
        line: SalesOrderLine,
        product: Product,
        outstanding: Decimal,
        overrides: Sequence[Any],
    ) -> LinePlan:
        plan = LinePlan(line=line, product=product, requested=outstanding)

        # Lock every stock row for this product before reading availability.
        rows = list(
            (
                await session.execute(
                    select(Inventory, Warehouse)
                    .join(Warehouse, Warehouse.id == Inventory.warehouse_id)
                    .where(
                        Inventory.organization_id == order.organization_id,
                        Inventory.product_id == product.id,
                        Warehouse.is_active.is_(True),
                    )
                    .order_by(Inventory.id)
                    .with_for_update(of=Inventory)
                )
            ).all()
        )
        stock = {inv.warehouse_id: (inv, wh) for inv, wh in rows}
        remaining = outstanding

        # -------------------------------------------------- manual overrides
        for entry in overrides:
            pair = stock.get(entry.warehouse_id)
            if pair is None:
                raise NotFoundError(
                    f"'{product.name}' is not stocked at the requested warehouse.",
                    details={"warehouse_id": str(entry.warehouse_id)},
                )
            inv, wh = pair
            requested = Decimal(entry.quantity)
            if requested > remaining:
                raise BusinessRuleError(
                    f"Override allocates {format_quantity(requested)} units of "
                    f"'{product.name}' but only {format_quantity(remaining)} are "
                    f"outstanding on this line.",
                    code="OVERRIDE_EXCEEDS_LINE",
                    details={"outstanding": str(remaining)},
                )
            available = Decimal(inv.quantity_on_hand) - Decimal(inv.quantity_reserved)
            if requested > available:
                raise InsufficientInventoryError(
                    f"{wh.name} has {format_quantity(available)} units of "
                    f"'{product.name}' available but the override requests "
                    f"{format_quantity(requested)}.",
                    details={
                        "warehouse": wh.name,
                        "available": str(available),
                        "requested": str(requested),
                    },
                )
            inv.quantity_reserved = Decimal(inv.quantity_reserved) + requested
            remaining -= requested
            plan.splits.append(
                Split(
                    warehouse_id=wh.id,
                    warehouse_code=wh.code,
                    warehouse_name=wh.name,
                    quantity=requested,
                )
            )

        if remaining <= ZERO:
            await session.flush()
            return plan

        # ------------------------------------------------ automatic strategy
        candidates = [
            (inv, wh)
            for inv, wh in stock.values()
            if Decimal(inv.quantity_on_hand) - Decimal(inv.quantity_reserved) > ZERO
        ]

        def availability(pair: tuple[Inventory, Warehouse]) -> Decimal:
            inv, _ = pair
            return Decimal(inv.quantity_on_hand) - Decimal(inv.quantity_reserved)

        single = [p for p in candidates if availability(p) >= remaining]
        if single:
            chosen = sorted(
                single,
                key=lambda p: (
                    p[1].priority,
                    p[1].shipping_cost_per_shipment,
                    -availability(p),
                    p[1].code,
                ),
            )[:1]
        else:
            chosen = sorted(
                candidates,
                key=lambda p: (
                    -availability(p),
                    p[1].priority,
                    p[1].shipping_cost_per_shipment,
                    p[1].code,
                ),
            )

        for inv, wh in chosen:
            if remaining <= ZERO:
                break
            take = min(availability((inv, wh)), remaining)
            if take <= ZERO:
                continue
            inv.quantity_reserved = Decimal(inv.quantity_reserved) + take
            remaining -= take
            plan.splits.append(
                Split(
                    warehouse_id=wh.id,
                    warehouse_code=wh.code,
                    warehouse_name=wh.name,
                    quantity=take,
                )
            )

        if remaining > ZERO:
            plan.splits.append(
                Split(
                    warehouse_id=None,
                    warehouse_code="BACKORDER",
                    warehouse_name="Backorder (awaiting restock)",
                    quantity=remaining,
                    backorder=True,
                )
            )

        await session.flush()
        return plan

    @staticmethod
    async def _earliest_restock(
        session: AsyncSession, organization_id: uuid.UUID, product_id: uuid.UUID
    ) -> datetime | None:
        return (
            await session.execute(
                select(func.min(Inventory.expected_restock_at)).where(
                    Inventory.organization_id == organization_id,
                    Inventory.product_id == product_id,
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    def _explain_plan(plan: LinePlan) -> str:
        real = [s for s in plan.splits if not s.backorder]
        back = [s for s in plan.splits if s.backorder]
        parts: list[str] = []
        if real:
            parts.append(
                "Sourced "
                + ", ".join(
                    f"{format_quantity(s.quantity)} from {s.warehouse_name}"
                    for s in real
                )
            )
            if len(real) == 1:
                parts.append("in a single shipment")
            else:
                parts.append(
                    f"across {len(real)} shipments because no single warehouse "
                    f"held all {format_quantity(plan.requested)} units"
                )
        if back:
            parts.append(
                f"{format_quantity(back[0].quantity)} unit(s) backordered — "
                f"no warehouse has stock"
            )
        return ("; ".join(parts) + ".") if parts else "Nothing to allocate."

    @classmethod
    async def _finalise(
        cls,
        session: AsyncSession,
        *,
        order: SalesOrder,
        actor: User,
        plans: Sequence[LinePlan],
        result_lines: Sequence[dict[str, Any]],
        shipment_count: int,
    ) -> dict[str, Any]:
        lines = list(
            (
                await session.execute(
                    select(SalesOrderLine).where(
                        SalesOrderLine.sales_order_id == order.id
                    )
                )
            ).scalars()
        )
        fully = all(
            Decimal(line.quantity_allocated) >= Decimal(line.quantity) for line in lines
        )
        has_backorder = any(
            Decimal(line.quantity_backordered) > ZERO for line in lines
        )

        order.fully_allocated = fully
        order.has_backorder = has_backorder
        order.allocated_at = datetime.now(UTC)
        if fully:
            order.status = SalesOrderStatus.ALLOCATED
        elif has_backorder and not any(
            Decimal(line.quantity_allocated) > ZERO for line in lines
        ):
            order.status = SalesOrderStatus.BACKORDERED
        else:
            order.status = SalesOrderStatus.PARTIALLY_ALLOCATED
        await session.flush()

        shipping_cost = ZERO
        for allocation, warehouse in await cls.allocations_for_order(session, order.id):
            if warehouse is not None and allocation.status is AllocationStatus.ALLOCATED:
                shipping_cost += Decimal(warehouse.shipping_cost_per_shipment)

        await AuditService.emit(
            session,
            EventType.INVENTORY_ALLOCATED,
            organization_id=order.organization_id,
            entity_type="sales_order",
            entity_id=order.id,
            actor=actor,
            payload={
                "order_number": order.order_number,
                "fully_allocated": fully,
                "has_backorder": has_backorder,
                "shipment_count": shipment_count,
                "lines": [
                    {
                        "product_name": entry["product_name"],
                        "quantity_allocated": str(entry["quantity_allocated"]),
                        "quantity_backordered": str(entry["quantity_backordered"]),
                        "splits": entry["splits"],
                    }
                    for entry in result_lines
                ],
            },
        )

        if has_backorder:
            shortfall = [
                entry
                for entry in result_lines
                if Decimal(entry["quantity_backordered"]) > ZERO
            ]
            detail_text = ", ".join(
                f"{format_quantity(entry['quantity_backordered'])} x "
                f"{entry['product_name']}"
                for entry in shortfall
            )
            await AuditService.emit(
                session,
                EventType.INVENTORY_SHORTAGE,
                organization_id=order.organization_id,
                entity_type="sales_order",
                entity_id=order.id,
                actor=actor,
                payload={"order_number": order.order_number, "shortfall": detail_text},
            )
            await AttentionService.upsert(
                session,
                organization_id=order.organization_id,
                source_type="sales_order",
                source_id=order.id,
                item_type=AttentionItemType.INVENTORY_SHORTAGE,
                severity=Severity.HIGH,
                title=f"Stock shortage on {order.order_number}",
                reason=f"Insufficient stock to fill the order: {detail_text}.",
                impact=(
                    "The order cannot ship complete; the backordered units are "
                    "waiting on a restock."
                ),
                owner_role=RoleCode.OPS,
                recommended_action=(
                    "Raise a purchase order or transfer stock, then re-run "
                    "allocation to consolidate the backorder."
                ),
                deal_id=order.deal_id,
                quote_id=order.quote_id,
                detail={"shortfall": detail_text},
                actor=actor,
            )
        else:
            await AttentionService.resolve(
                session,
                organization_id=order.organization_id,
                source_type="sales_order",
                source_id=order.id,
                item_type=AttentionItemType.INVENTORY_SHORTAGE,
                note="All lines fully allocated.",
                actor=actor,
            )

        message = (
            f"Allocated across {shipment_count} warehouse(s)."
            if fully
            else "Partially allocated; the remainder is on backorder."
        )
        return {
            "sales_order_id": order.id,
            "status": order.status.value,
            "fully_allocated": fully,
            "has_backorder": has_backorder,
            "shipment_count": shipment_count,
            "estimated_shipping_cost": money(shipping_cost),
            "lines": list(result_lines),
            "idempotent_replay": False,
            "message": message,
        }

    # -------------------------------------------------------- consolidation
    @classmethod
    async def consolidate_backorders(
        cls,
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        product_id: uuid.UUID,
        actor: User,
    ) -> list[uuid.UUID]:
        """After a restock, fill backorders oldest-first.

        Returns the ids of orders whose allocation changed.
        """
        pending = list(
            (
                await session.execute(
                    select(InventoryAllocation)
                    .where(
                        InventoryAllocation.organization_id == organization_id,
                        InventoryAllocation.product_id == product_id,
                        InventoryAllocation.status == AllocationStatus.BACKORDERED,
                    )
                    .order_by(InventoryAllocation.created_at)
                    .with_for_update()
                )
            ).scalars()
        )
        touched: list[uuid.UUID] = []

        for allocation in pending:
            order = await session.get(SalesOrder, allocation.sales_order_id)
            line = await session.get(SalesOrderLine, allocation.sales_order_line_id)
            if order is None or line is None:
                continue
            product = await session.get(Product, product_id)
            assert product is not None

            # Reverse the backorder, then re-plan the same quantity.
            quantity = Decimal(allocation.quantity)
            line.quantity_backordered = Decimal(line.quantity_backordered) - quantity
            line.quantity_allocated = Decimal(line.quantity_allocated) - ZERO
            await session.delete(allocation)
            await session.flush()

            plan = await cls._plan_line(
                session,
                order=order,
                line=line,
                product=product,
                outstanding=quantity,
                overrides=(),
            )
            for split in plan.splits:
                inventory_id: uuid.UUID | None = None
                if not split.backorder and split.warehouse_id is not None:
                    inv = (
                        await session.execute(
                            select(Inventory).where(
                                Inventory.warehouse_id == split.warehouse_id,
                                Inventory.product_id == product_id,
                            )
                        )
                    ).scalar_one()
                    inventory_id = inv.id
                session.add(
                    InventoryAllocation(
                        organization_id=organization_id,
                        sales_order_id=order.id,
                        sales_order_line_id=line.id,
                        product_id=product_id,
                        warehouse_id=split.warehouse_id,
                        inventory_id=inventory_id,
                        quantity=split.quantity,
                        status=(
                            AllocationStatus.BACKORDERED
                            if split.backorder
                            else AllocationStatus.ALLOCATED
                        ),
                        mode=AllocationMode.AUTOMATIC,
                        allocated_by_user_id=actor.id,
                        notes="Consolidated after restock." if not split.backorder else None,
                    )
                )
            line.quantity_allocated = Decimal(line.quantity_allocated) + plan.allocated
            line.quantity_backordered = (
                Decimal(line.quantity_backordered) + plan.backordered
            )
            await session.flush()

            if plan.allocated > ZERO:
                touched.append(order.id)
                await cls._finalise(
                    session,
                    order=order,
                    actor=actor,
                    plans=[plan],
                    result_lines=[
                        {
                            "sales_order_line_id": line.id,
                            "product_id": product_id,
                            "product_name": product.name,
                            "quantity_requested": quantity,
                            "quantity_allocated": plan.allocated,
                            "quantity_backordered": plan.backordered,
                            "splits": [
                                {
                                    "warehouse_code": s.warehouse_code,
                                    "warehouse_name": s.warehouse_name,
                                    "quantity": str(s.quantity),
                                    "status": (
                                        "BACKORDERED" if s.backorder else "ALLOCATED"
                                    ),
                                }
                                for s in plan.splits
                            ],
                            "explanation": cls._explain_plan(plan),
                        }
                    ],
                    shipment_count=len(
                        {s.warehouse_id for s in plan.splits if not s.backorder}
                    ),
                )
        return touched

    # ------------------------------------------------------------- fulfil
    @classmethod
    async def fulfill_order(
        cls,
        session: AsyncSession,
        *,
        order: SalesOrder,
        actor: User,
        warehouse_id: uuid.UUID | None = None,
        carrier: str | None = None,
        tracking_number: str | None = None,
    ) -> list[Fulfillment]:
        """Ship allocated stock: one fulfilment per warehouse."""
        allocations = [
            (a, w)
            for a, w in await cls.allocations_for_order(session, order.id)
            if a.status is AllocationStatus.ALLOCATED
            and (warehouse_id is None or a.warehouse_id == warehouse_id)
        ]
        if not allocations:
            raise ConflictError(
                "There is no allocated stock to fulfil on this order. Allocate first.",
                code="NOTHING_TO_FULFILL",
            )

        by_warehouse: dict[uuid.UUID, list[tuple[InventoryAllocation, Warehouse]]] = {}
        for allocation, warehouse in allocations:
            assert warehouse is not None
            by_warehouse.setdefault(warehouse.id, []).append((allocation, warehouse))

        existing = (
            await session.execute(
                select(func.count())
                .select_from(Fulfillment)
                .where(Fulfillment.sales_order_id == order.id)
            )
        ).scalar_one()
        sequence = int(existing)
        created: list[Fulfillment] = []
        now = datetime.now(UTC)

        for wh_id, entries in by_warehouse.items():
            sequence += 1
            warehouse = entries[0][1]
            fulfillment = Fulfillment(
                organization_id=order.organization_id,
                fulfillment_number=f"{order.order_number}-S{sequence:02d}",
                sales_order_id=order.id,
                warehouse_id=wh_id,
                shipment_sequence=sequence,
                status=FulfillmentStatus.SHIPPED,
                carrier=carrier,
                tracking_number=tracking_number,
                shipping_cost=Decimal(warehouse.shipping_cost_per_shipment),
                shipped_at=now,
            )
            session.add(fulfillment)
            await session.flush()

            for allocation, _ in entries:
                inv = (
                    await session.execute(
                        select(Inventory)
                        .where(
                            Inventory.warehouse_id == wh_id,
                            Inventory.product_id == allocation.product_id,
                        )
                        .with_for_update()
                    )
                ).scalar_one()
                quantity = Decimal(allocation.quantity)
                # Shipping converts a reservation into an outbound movement.
                inv.quantity_on_hand = Decimal(inv.quantity_on_hand) - quantity
                inv.quantity_reserved = Decimal(inv.quantity_reserved) - quantity

                allocation.status = AllocationStatus.SHIPPED
                allocation.fulfillment_id = fulfillment.id

                line = await session.get(SalesOrderLine, allocation.sales_order_line_id)
                if line is not None:
                    line.quantity_fulfilled = (
                        Decimal(line.quantity_fulfilled) + quantity
                    )
            created.append(fulfillment)

        await session.flush()

        lines = list(
            (
                await session.execute(
                    select(SalesOrderLine).where(
                        SalesOrderLine.sales_order_id == order.id
                    )
                )
            ).scalars()
        )
        stock_lines = [line for line in lines if line.is_stock_tracked]
        all_shipped = all(
            Decimal(line.quantity_fulfilled) >= Decimal(line.quantity)
            for line in stock_lines
        )
        order.status = (
            SalesOrderStatus.FULFILLED
            if all_shipped
            else SalesOrderStatus.PARTIALLY_FULFILLED
        )
        if all_shipped:
            order.fulfilled_at = now
        await session.flush()

        await AuditService.emit(
            session,
            EventType.ORDER_FULFILLED,
            organization_id=order.organization_id,
            entity_type="sales_order",
            entity_id=order.id,
            actor=actor,
            payload={
                "order_number": order.order_number,
                "shipments": [
                    {
                        "fulfillment_number": f.fulfillment_number,
                        "warehouse_id": str(f.warehouse_id),
                        "shipping_cost": str(f.shipping_cost),
                    }
                    for f in created
                ],
                "order_status": order.status.value,
            },
        )
        return created

    # ------------------------------------------------------------- delivery
    @classmethod
    async def confirm_delivery(
        cls,
        session: AsyncSession,
        *,
        order: SalesOrder,
        fulfillment_id: uuid.UUID,
        actor: User,
        delivered_at: datetime | None = None,
        note: str | None = None,
    ) -> Fulfillment:
        """Mark a shipment delivered.

        ``FulfillmentStatus.DELIVERED`` was previously unreachable, which meant
        PDF B9.3's slippage indicator had no completion signal to measure
        against: a shipment sitting in transit for a month looked identical to
        one that arrived the next day.
        """
        fulfillment = await session.get(Fulfillment, fulfillment_id)
        if (
            fulfillment is None
            or fulfillment.sales_order_id != order.id
            or fulfillment.organization_id != order.organization_id
        ):
            raise NotFoundError("Fulfilment not found on this order.")
        if fulfillment.status is FulfillmentStatus.DELIVERED:
            raise ConflictError(
                "This shipment is already confirmed delivered.",
                code="ALREADY_DELIVERED",
                details={"fulfillment_number": fulfillment.fulfillment_number},
            )
        if fulfillment.status is not FulfillmentStatus.SHIPPED:
            raise ConflictError(
                f"A {fulfillment.status.value} shipment cannot be marked "
                f"delivered.",
                code="FULFILLMENT_NOT_SHIPPED",
                details={"status": fulfillment.status.value},
            )

        when = delivered_at or datetime.now(UTC)
        fulfillment.status = FulfillmentStatus.DELIVERED
        fulfillment.delivered_at = when
        if note:
            fulfillment.notes = note
        await session.flush()

        siblings = list(
            (
                await session.execute(
                    select(Fulfillment).where(
                        Fulfillment.sales_order_id == order.id
                    )
                )
            ).scalars()
        )
        all_delivered = all(
            f.status is FulfillmentStatus.DELIVERED for f in siblings
        )

        promised = order.promised_delivery_date
        late_by = (
            (when.date() - promised).days
            if promised is not None and when.date() > promised
            else 0
        )

        await AuditService.emit(
            session,
            EventType.ORDER_DELIVERED,
            organization_id=order.organization_id,
            entity_type="sales_order",
            entity_id=order.id,
            actor=actor,
            payload={
                "order_number": order.order_number,
                "fulfillment_number": fulfillment.fulfillment_number,
                "delivered_at": when.isoformat(),
                "promised_delivery_date": (
                    promised.isoformat() if promised else None
                ),
                "days_late": late_by,
                "all_shipments_delivered": all_delivered,
                "note": note,
            },
        )

        if all_delivered:
            # Delivery closes the slippage question for this order either way.
            await AttentionService.resolve(
                session,
                organization_id=order.organization_id,
                source_type="sales_order",
                source_id=order.id,
                item_type=AttentionItemType.DELIVERY_SLIPPAGE,
                note=(
                    f"All shipments delivered {when.date().isoformat()}"
                    + (f", {late_by} day(s) late." if late_by else " on time.")
                ),
                actor=actor,
            )
        return fulfillment

    # --------------------------------------------------------------- cancel
    @classmethod
    async def cancel_order(
        cls,
        session: AsyncSession,
        *,
        order: SalesOrder,
        actor: User,
        reason: str,
    ) -> SalesOrder:
        """Cancel an order and release every outstanding reservation.

        Releasing matters more than the status change: a reservation holds
        ``quantity_reserved`` against real stock, so an order abandoned after
        allocation would otherwise make that stock permanently unsellable while
        appearing available in no report.
        """
        if order.status is SalesOrderStatus.CANCELLED:
            raise ConflictError(
                "This order is already cancelled.",
                code="ORDER_ALREADY_CANCELLED",
                details={"order_number": order.order_number},
            )
        shipped = (
            await session.execute(
                select(func.count())
                .select_from(InventoryAllocation)
                .where(
                    InventoryAllocation.sales_order_id == order.id,
                    InventoryAllocation.status == AllocationStatus.SHIPPED,
                )
            )
        ).scalar_one()
        if int(shipped):
            raise ConflictError(
                "Stock has already shipped on this order, so it cannot be "
                "cancelled. Raise a credit note or return instead.",
                code="ORDER_ALREADY_SHIPPED",
                details={"shipped_allocations": int(shipped)},
            )

        allocations = list(
            (
                await session.execute(
                    select(InventoryAllocation).where(
                        InventoryAllocation.sales_order_id == order.id,
                        InventoryAllocation.status.in_(
                            (
                                AllocationStatus.RESERVED,
                                AllocationStatus.ALLOCATED,
                                AllocationStatus.BACKORDERED,
                            )
                        ),
                    )
                )
            ).scalars()
        )

        released = ZERO
        now = datetime.now(UTC)
        for allocation in allocations:
            quantity = Decimal(allocation.quantity)
            if allocation.warehouse_id is not None:
                inv = (
                    await session.execute(
                        select(Inventory)
                        .where(
                            Inventory.warehouse_id == allocation.warehouse_id,
                            Inventory.product_id == allocation.product_id,
                        )
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if inv is not None:
                    inv.quantity_reserved = max(
                        ZERO, Decimal(inv.quantity_reserved) - quantity
                    )
                    released += quantity
                allocation.status = AllocationStatus.RELEASED
            else:
                # A backorder never reserved anything, so there is nothing to
                # give back — it is simply cancelled.
                allocation.status = AllocationStatus.CANCELLED
            allocation.released_at = now

        for line in (
            await session.execute(
                select(SalesOrderLine).where(
                    SalesOrderLine.sales_order_id == order.id
                )
            )
        ).scalars():
            line.quantity_allocated = ZERO
            line.quantity_backordered = ZERO

        order.status = SalesOrderStatus.CANCELLED
        order.fully_allocated = False
        order.has_backorder = False
        order.allocated_at = None

        # Cancel any schedule that has not already been invoiced.
        for schedule in (
            await session.execute(
                select(BillingSchedule).where(
                    BillingSchedule.sales_order_id == order.id,
                    BillingSchedule.status.in_(
                        (
                            BillingScheduleStatus.SCHEDULED,
                            BillingScheduleStatus.ACTIVE,
                        )
                    ),
                )
            )
        ).scalars():
            schedule.status = BillingScheduleStatus.CANCELLED

        await session.flush()

        for item_type in (
            AttentionItemType.INVENTORY_SHORTAGE,
            AttentionItemType.DELIVERY_SLIPPAGE,
            AttentionItemType.ORDER_BLOCKED,
        ):
            await AttentionService.resolve(
                session,
                organization_id=order.organization_id,
                source_type="sales_order",
                source_id=order.id,
                item_type=item_type,
                note="Order was cancelled.",
                actor=actor,
            )

        await AuditService.emit(
            session,
            EventType.ORDER_CANCELLED,
            organization_id=order.organization_id,
            entity_type="sales_order",
            entity_id=order.id,
            actor=actor,
            payload={
                "order_number": order.order_number,
                "reason": reason,
                "allocations_released": len(allocations),
                "quantity_released": str(released),
            },
        )
        return order
