"""Warehouse and inventory read endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.dependencies import DbSession, InternalUser
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.warehouse import Warehouse
from app.schemas.inventory import InventoryRead, WarehouseRead

router = APIRouter(tags=["inventory"])


@router.get(
    "/warehouses", response_model=list[WarehouseRead], summary="List warehouses"
)
async def list_warehouses(user: InternalUser, db: DbSession) -> list[WarehouseRead]:
    rows = (
        await db.execute(
            select(Warehouse)
            .where(Warehouse.organization_id == user.organization_id)
            .order_by(Warehouse.priority, Warehouse.code)
        )
    ).scalars()
    return [WarehouseRead.model_validate(w) for w in rows]


@router.get(
    "/inventory",
    response_model=list[InventoryRead],
    summary="Stock levels, with available = on_hand - reserved",
)
async def list_inventory(
    user: InternalUser,
    db: DbSession,
    product_id: uuid.UUID | None = Query(default=None),
    warehouse_id: uuid.UUID | None = Query(default=None),
) -> list[InventoryRead]:
    stmt = (
        select(Inventory, Warehouse, Product)
        .join(Warehouse, Warehouse.id == Inventory.warehouse_id)
        .join(Product, Product.id == Inventory.product_id)
        .where(Inventory.organization_id == user.organization_id)
    )
    if product_id is not None:
        stmt = stmt.where(Inventory.product_id == product_id)
    if warehouse_id is not None:
        stmt = stmt.where(Inventory.warehouse_id == warehouse_id)
    stmt = stmt.order_by(Product.name, Warehouse.priority, Warehouse.code)

    return [
        InventoryRead(
            id=inv.id,
            created_at=inv.created_at,
            updated_at=inv.updated_at,
            warehouse_id=inv.warehouse_id,
            warehouse_code=wh.code,
            warehouse_name=wh.name,
            product_id=inv.product_id,
            product_sku=prod.sku,
            product_name=prod.name,
            quantity_on_hand=inv.quantity_on_hand,
            quantity_reserved=inv.quantity_reserved,
            quantity_available=inv.quantity_available,
            quantity_inbound=inv.quantity_inbound,
            reorder_point=inv.reorder_point,
            expected_restock_at=inv.expected_restock_at,
        )
        for inv, wh, prod in (await db.execute(stmt)).all()
    ]
