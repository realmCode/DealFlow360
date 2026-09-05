"""Administrative configuration: catalog, warehouses, stock, policies, seed."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status
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
    WarehouseUpdate,
)
from app.schemas.policy import PolicyCreate, PolicyRead, PolicyUpdate
from app.schemas.product import (
    PriceListCreate,
    PriceListRead,
    PriceListUpdate,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantRead,
    ProductVariantUpdate,
)
from app.schemas.reporting import (
    OrganizationSettingsRead,
    OrganizationSettingsUpdate,
    SalesTeamCreate,
    SalesTeamMemberAdd,
    SalesTeamRead,
    SalesTeamUpdate,
)
from app.services.inventory_service import InventoryService
from app.services.sales_team_service import SalesTeamService
from app.services.settings_service import SettingsService

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


# ------------------------------------------------------- variants (reads)
@router.get(
    "/product-variants",
    response_model=list[ProductVariantRead],
    summary="List product variants",
)
async def list_variants(
    admin: AdminUser,
    db: DbSession,
    product_id: uuid.UUID | None = Query(default=None),
    include_inactive: bool = Query(default=False),
) -> list[ProductVariantRead]:
    """Without this, an admin could create variants and never see them again."""
    stmt = select(ProductVariant).where(
        ProductVariant.organization_id == admin.organization_id
    )
    if product_id is not None:
        stmt = stmt.where(ProductVariant.product_id == product_id)
    if not include_inactive:
        stmt = stmt.where(ProductVariant.is_active.is_(True))
    rows = (await db.execute(stmt.order_by(ProductVariant.sku))).scalars()
    return [ProductVariantRead.model_validate(v) for v in rows]


@router.patch(
    "/product-variants/{variant_id}",
    response_model=ProductVariantRead,
    summary="Update a product variant",
)
async def update_variant(
    variant_id: uuid.UUID,
    payload: ProductVariantUpdate,
    admin: AdminUser,
    db: DbSession,
) -> ProductVariantRead:
    variant = await db.get(ProductVariant, variant_id)
    if variant is None or variant.organization_id != admin.organization_id:
        raise NotFoundError("Product variant not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(variant, key, value)
    await db.flush()
    await db.commit()
    return ProductVariantRead.model_validate(variant)


# ----------------------------------------------------- price lists (reads)
@router.get(
    "/price-lists",
    response_model=list[PriceListRead],
    summary="List tier price lists",
)
async def list_price_lists(
    admin: AdminUser,
    db: DbSession,
    include_inactive: bool = Query(default=False),
) -> list[PriceListRead]:
    stmt = select(PriceList).where(
        PriceList.organization_id == admin.organization_id
    )
    if not include_inactive:
        stmt = stmt.where(PriceList.is_active.is_(True))
    rows = (await db.execute(stmt.order_by(PriceList.code))).scalars()
    return [PriceListRead.model_validate(p) for p in rows]


@router.patch(
    "/price-lists/{price_list_id}",
    response_model=PriceListRead,
    summary="Update a tier price list",
)
async def update_price_list(
    price_list_id: uuid.UUID,
    payload: PriceListUpdate,
    admin: AdminUser,
    db: DbSession,
) -> PriceListRead:
    price_list = await db.get(PriceList, price_list_id)
    if price_list is None or price_list.organization_id != admin.organization_id:
        raise NotFoundError("Price list not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(price_list, key, value)
    await db.flush()
    await db.commit()
    return PriceListRead.model_validate(price_list)


# ------------------------------------------------------ warehouses (edit)
@router.get(
    "/warehouses/{warehouse_id}",
    response_model=WarehouseRead,
    summary="Get one warehouse",
)
async def get_warehouse(
    warehouse_id: uuid.UUID, admin: AdminUser, db: DbSession
) -> WarehouseRead:
    warehouse = await db.get(Warehouse, warehouse_id)
    if warehouse is None or warehouse.organization_id != admin.organization_id:
        raise NotFoundError("Warehouse not found.")
    return WarehouseRead.model_validate(warehouse)


@router.patch(
    "/warehouses/{warehouse_id}",
    response_model=WarehouseRead,
    summary="Update a warehouse (priority and shipping cost drive the split)",
)
async def update_warehouse(
    warehouse_id: uuid.UUID,
    payload: WarehouseUpdate,
    admin: AdminUser,
    db: DbSession,
) -> WarehouseRead:
    """A warehouse could previously be created but never edited, so a wrong
    shipping cost or priority — both of which drive the allocation split —
    was permanent."""
    warehouse = await db.get(Warehouse, warehouse_id)
    if warehouse is None or warehouse.organization_id != admin.organization_id:
        raise NotFoundError("Warehouse not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(warehouse, key, value)
    await db.flush()
    await db.commit()
    return WarehouseRead.model_validate(warehouse)


# -------------------------------------------------------------- settings
@router.get(
    "/settings",
    response_model=OrganizationSettingsRead,
    summary="Governance settings for your organization",
)
async def get_settings(admin: AdminUser, db: DbSession) -> OrganizationSettingsRead:
    """PDF A3/B9 — the approval chain and stalled-deal window are per-tenant."""
    row = await SettingsService.for_org(db, admin.organization_id)
    await db.commit()
    return OrganizationSettingsRead.model_validate(row)


@router.patch(
    "/settings",
    response_model=OrganizationSettingsRead,
    summary="Update governance thresholds and risk weights",
)
async def update_settings(
    payload: OrganizationSettingsUpdate, admin: AdminUser, db: DbSession
) -> OrganizationSettingsRead:
    row = await SettingsService.for_org(db, admin.organization_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(row, key, value)
    await db.flush()
    await db.commit()
    return OrganizationSettingsRead.model_validate(row)


# ----------------------------------------------------------- sales teams
@router.post(
    "/sales-teams",
    response_model=SalesTeamRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a sales team (enables the Sales Team report filter)",
)
async def create_sales_team(
    payload: SalesTeamCreate, admin: AdminUser, db: DbSession
) -> SalesTeamRead:
    team = await SalesTeamService.create(
        db,
        organization_id=admin.organization_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        manager_user_id=payload.manager_user_id,
        region=payload.region,
        member_user_ids=payload.member_user_ids,
    )
    await db.commit()
    return SalesTeamRead.model_validate(await SalesTeamService.to_read(db, team))


@router.get(
    "/sales-teams",
    response_model=list[SalesTeamRead],
    summary="List sales teams and their members",
)
async def list_sales_teams(
    admin: AdminUser,
    db: DbSession,
    include_inactive: bool = Query(default=False),
) -> list[SalesTeamRead]:
    teams = await SalesTeamService.list_teams(
        db, admin.organization_id, include_inactive=include_inactive
    )
    return [
        SalesTeamRead.model_validate(await SalesTeamService.to_read(db, t))
        for t in teams
    ]


@router.patch(
    "/sales-teams/{team_id}",
    response_model=SalesTeamRead,
    summary="Update a sales team",
)
async def update_sales_team(
    team_id: uuid.UUID,
    payload: SalesTeamUpdate,
    admin: AdminUser,
    db: DbSession,
) -> SalesTeamRead:
    team = await SalesTeamService.get(db, team_id, admin.organization_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(team, key, value)
    await db.flush()
    await db.commit()
    return SalesTeamRead.model_validate(await SalesTeamService.to_read(db, team))


@router.post(
    "/sales-teams/{team_id}/members",
    response_model=SalesTeamRead,
    summary="Add members to a sales team",
)
async def add_sales_team_members(
    team_id: uuid.UUID,
    payload: SalesTeamMemberAdd,
    admin: AdminUser,
    db: DbSession,
) -> SalesTeamRead:
    team = await SalesTeamService.get(db, team_id, admin.organization_id)
    await SalesTeamService.add_members(
        db,
        team=team,
        user_ids=payload.user_ids,
        organization_id=admin.organization_id,
    )
    await db.commit()
    return SalesTeamRead.model_validate(await SalesTeamService.to_read(db, team))


@router.delete(
    "/sales-teams/{team_id}/members/{user_id}",
    response_model=SalesTeamRead,
    summary="Remove a member from a sales team",
)
async def remove_sales_team_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    admin: AdminUser,
    db: DbSession,
) -> SalesTeamRead:
    team = await SalesTeamService.get(db, team_id, admin.organization_id)
    await SalesTeamService.remove_member(db, team=team, user_id=user_id)
    await db.commit()
    return SalesTeamRead.model_validate(await SalesTeamService.to_read(db, team))


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
