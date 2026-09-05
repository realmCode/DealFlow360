"""Catalog read endpoints (all internal roles)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.dependencies import DbSession, InternalUser
from app.enums import ProductCategory
from app.errors import NotFoundError
from app.models.product import Product, ProductVariant
from app.schemas.common import Page
from app.schemas.product import ProductRead, ProductVariantRead
from app.schemas.query import Pagination, Sorting

router = APIRouter(tags=["products"])

PRODUCT_SORTABLE = {
    "name": Product.name,
    "sku": Product.sku,
    "category": Product.category,
    "list_price": Product.list_price,
    "created_at": Product.created_at,
}


def _to_read(product: Product) -> ProductRead:
    return ProductRead(
        id=product.id,
        created_at=product.created_at,
        updated_at=product.updated_at,
        sku=product.sku,
        name=product.name,
        description=product.description,
        category=product.category,
        list_price=product.list_price,
        internal_cost=product.internal_cost,
        tax_rate_pct=product.tax_rate_pct,
        uom=product.uom,
        billing_type=product.billing_type,
        recurring_interval=product.recurring_interval,
        default_recurring_periods=product.default_recurring_periods,
        is_stock_tracked=product.is_stock_tracked,
        is_active=product.is_active,
        is_promoted=product.is_promoted,
        unit_margin=product.unit_margin,
    )


@router.get(
    "/products",
    response_model=Page[ProductRead],
    summary="List the catalog (paginated, filterable, searchable)",
)
async def list_products(
    user: InternalUser,
    db: DbSession,
    page: Pagination,
    sort: Sorting,
    category: ProductCategory | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    is_promoted: bool | None = Query(
        default=None, description="Only promoted products (PDF A6.2)."
    ),
    is_stock_tracked: bool | None = Query(default=None),
    q: str | None = Query(
        default=None, max_length=128, description="Search SKU or name."
    ),
) -> Page[ProductRead]:
    stmt = select(Product).where(Product.organization_id == user.organization_id)
    if category is not None:
        stmt = stmt.where(Product.category == category)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    if is_promoted is not None:
        stmt = stmt.where(Product.is_promoted.is_(is_promoted))
    if is_stock_tracked is not None:
        stmt = stmt.where(Product.is_stock_tracked.is_(is_stock_tracked))
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(Product.sku.ilike(needle) | Product.name.ilike(needle))

    total = (
        await db.execute(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
    ).scalar_one()

    column, descending = sort.resolve(PRODUCT_SORTABLE, default="name")
    # Category first keeps the builder's grouped product picker stable.
    stmt = stmt.order_by(
        Product.category, column.desc() if descending else column.asc()
    )
    rows = (
        await db.execute(stmt.limit(page.limit).offset(page.offset))
    ).scalars()

    return Page[ProductRead](
        items=[_to_read(p) for p in rows],
        total=int(total),
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/products/{product_id}", response_model=ProductRead, summary="Get one product"
)
async def get_product(
    product_id: uuid.UUID, user: InternalUser, db: DbSession
) -> ProductRead:
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != user.organization_id:
        raise NotFoundError("Product not found.")
    return _to_read(product)


@router.get(
    "/products/{product_id}/variants",
    response_model=list[ProductVariantRead],
    summary="Variants available for a product",
)
async def product_variants(
    product_id: uuid.UUID, user: InternalUser, db: DbSession
) -> list[ProductVariantRead]:
    """The quote builder needs this to offer variant selection on a line.

    Previously variants could only be created, never listed, so nothing could
    present them for selection.
    """
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != user.organization_id:
        raise NotFoundError("Product not found.")
    rows = (
        await db.execute(
            select(ProductVariant)
            .where(
                ProductVariant.product_id == product_id,
                ProductVariant.is_active.is_(True),
            )
            .order_by(ProductVariant.sku)
        )
    ).scalars()
    return [ProductVariantRead.model_validate(v) for v in rows]
