"""Administrative configuration: catalog, warehouses, stock, policies, seed."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.dependencies import AdminUser, DbSession
from app.errors import ConflictError, NotFoundError
from app.models.policy import Policy
from app.models.product import PriceList, Product, ProductVariant
from app.models.warehouse import Warehouse
from app.schemas.inventory import (
    InventoryAdjust,
    InventoryRead,
    InventoryUpsert,
    WarehouseCreate,
    WarehouseRead,
)
from app.schemas.policy import PolicyCreate, PolicyRead, PolicyUpdate
from app.schemas.product import (
    PriceListCreate,
    PriceListRead,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantRead,
)
from app.services.inventory_service import InventoryService

router = APIRouter(prefix="/admin", tags=["admin"])


# ------------------------------------------------------------------ products
@router.post(
    "/products",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a catalog product",
)
async def create_product(
    payload: ProductCreate, admin: AdminUser, db: DbSession
) -> ProductRead:
    duplicate = (
        await db.execute(
            select(Product.id).where(
                Product.organization_id == admin.organization_id,
                Product.sku == payload.sku,
            )
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise ConflictError(
            f"SKU {payload.sku} already exists.", code="SKU_EXISTS"
        )

    product = Product(
        organization_id=admin.organization_id, **payload.model_dump()
    )
    db.add(product)
    await db.flush()
    await db.commit()
    return ProductRead.model_validate(product)


@router.patch(
    "/products/{product_id}", response_model=ProductRead, summary="Update a product"
)
async def update_product(
    product_id: uuid.UUID, payload: ProductUpdate, admin: AdminUser, db: DbSession
) -> ProductRead:
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != admin.organization_id:
        raise NotFoundError("Product not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(product, key, value)
    await db.flush()
    await db.commit()
    return ProductRead.model_validate(product)


# ---------------------------------------------------------------- warehouses
@router.post(
    "/warehouses",
    response_model=WarehouseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a warehouse",
)
async def create_warehouse(
    payload: WarehouseCreate, admin: AdminUser, db: DbSession
) -> WarehouseRead:
    duplicate = (
        await db.execute(
            select(Warehouse.id).where(
                Warehouse.organization_id == admin.organization_id,
                Warehouse.code == payload.code,
            )
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise ConflictError(
            f"Warehouse code {payload.code} already exists.",
            code="WAREHOUSE_CODE_EXISTS",
        )
    warehouse = Warehouse(
        organization_id=admin.organization_id, **payload.model_dump()
    )
    db.add(warehouse)
    await db.flush()
    await db.commit()
    return WarehouseRead.model_validate(warehouse)


# ----------------------------------------------------------------- inventory
@router.post(
    "/inventory",
    response_model=InventoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Set stock on hand for a warehouse/product pair",
)
async def upsert_inventory(
    payload: InventoryUpsert, admin: AdminUser, db: DbSession
) -> InventoryRead:
    row = await InventoryService.upsert_stock(
        db,
        organization_id=admin.organization_id,
        warehouse_id=payload.warehouse_id,
        product_id=payload.product_id,
        quantity_on_hand=payload.quantity_on_hand,
        quantity_inbound=payload.quantity_inbound,
        reorder_point=payload.reorder_point,
        expected_restock_at=payload.expected_restock_at,
    )
    await db.commit()
    return await _inventory_read(db, row)


@router.post(
    "/inventory/adjust",
    response_model=InventoryRead,
    summary="Apply a stock movement; a receipt also consolidates backorders",
)
async def adjust_inventory(
    payload: InventoryAdjust, admin: AdminUser, db: DbSession
) -> InventoryRead:
    row = await InventoryService.adjust_stock(
        db,
        organization_id=admin.organization_id,
        warehouse_id=payload.warehouse_id,
        product_id=payload.product_id,
        delta=payload.quantity_delta,
        reason=payload.reason,
        actor=admin,
    )
    if payload.quantity_delta > 0:
        await InventoryService.consolidate_backorders(
            db,
            organization_id=admin.organization_id,
            product_id=payload.product_id,
            actor=admin,
        )
    await db.commit()
    return await _inventory_read(db, row)


async def _inventory_read(db, row) -> InventoryRead:  # noqa: ANN001
    warehouse = await db.get(Warehouse, row.warehouse_id)
    product = await db.get(Product, row.product_id)
    return InventoryRead(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        warehouse_id=row.warehouse_id,
        warehouse_code=warehouse.code if warehouse else None,
        warehouse_name=warehouse.name if warehouse else None,
        product_id=row.product_id,
        product_sku=product.sku if product else None,
        product_name=product.name if product else None,
        quantity_on_hand=row.quantity_on_hand,
        quantity_reserved=row.quantity_reserved,
        quantity_available=row.quantity_available,
        quantity_inbound=row.quantity_inbound,
        reorder_point=row.reorder_point,
        expected_restock_at=row.expected_restock_at,
    )


# ------------------------------------------------------------------ policies
@router.post(
    "/policies",
    response_model=PolicyRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a governance policy",
)
async def create_policy(
    payload: PolicyCreate, admin: AdminUser, db: DbSession
) -> PolicyRead:
    duplicate = (
        await db.execute(
            select(Policy.id).where(
                Policy.organization_id == admin.organization_id,
                Policy.code == payload.code,
            )
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise ConflictError(
            f"Policy code {payload.code} already exists.", code="POLICY_CODE_EXISTS"
        )
    policy = Policy(organization_id=admin.organization_id, **payload.model_dump())
    db.add(policy)
    await db.flush()
    await db.commit()
    return PolicyRead.model_validate(policy)


@router.patch(
    "/policies/{policy_id}", response_model=PolicyRead, summary="Update a policy"
)
async def update_policy(
    policy_id: uuid.UUID, payload: PolicyUpdate, admin: AdminUser, db: DbSession
) -> PolicyRead:
    policy = await db.get(Policy, policy_id)
    if policy is None or policy.organization_id != admin.organization_id:
        raise NotFoundError("Policy not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(policy, key, value)
    await db.flush()
    await db.commit()
    return PolicyRead.model_validate(policy)


# ----------------------------------------------------------------- P1 config
@router.post(
    "/product-variants",
    response_model=ProductVariantRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product variant (P1)",
)
async def create_variant(
    payload: ProductVariantCreate, admin: AdminUser, db: DbSession
) -> ProductVariantRead:
    product = await db.get(Product, payload.product_id)
    if product is None or product.organization_id != admin.organization_id:
        raise NotFoundError("Product not found.")
    variant = ProductVariant(
        organization_id=admin.organization_id, **payload.model_dump()
    )
    db.add(variant)
    await db.flush()
    await db.commit()
    return ProductVariantRead.model_validate(variant)


@router.post(
    "/price-lists",
    response_model=PriceListRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tier price list (P1)",
)
async def create_price_list(
    payload: PriceListCreate, admin: AdminUser, db: DbSession
) -> PriceListRead:
    price_list = PriceList(
        organization_id=admin.organization_id, **payload.model_dump()
    )
    db.add(price_list)
    await db.flush()
    await db.commit()
    return PriceListRead.model_validate(price_list)


# ---------------------------------------------------------------------- seed
@router.post(
    "/seed",
    summary="Load the canonical demo dataset (idempotent — safe to re-run)",
)
async def seed(admin: AdminUser, db: DbSession) -> dict[str, object]:
    from scripts.seed import seed_canonical_data

    result = await seed_canonical_data(db)
    await db.commit()
    return result
