"""Catalog read endpoints (all internal roles)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.dependencies import DbSession, InternalUser
from app.enums import ProductCategory
from app.errors import NotFoundError
from app.models.product import Product
from app.schemas.product import ProductRead

router = APIRouter(tags=["products"])


@router.get("/products", response_model=list[ProductRead], summary="List the catalog")
async def list_products(
    user: InternalUser,
    db: DbSession,
    category: ProductCategory | None = Query(default=None),
    include_inactive: bool = Query(default=False),
) -> list[ProductRead]:
    stmt = select(Product).where(Product.organization_id == user.organization_id)
    if category is not None:
        stmt = stmt.where(Product.category == category)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    stmt = stmt.order_by(Product.category, Product.name)
    return [ProductRead.model_validate(p) for p in (await db.execute(stmt)).scalars()]


@router.get(
    "/products/{product_id}", response_model=ProductRead, summary="Get one product"
)
async def get_product(
    product_id: uuid.UUID, user: InternalUser, db: DbSession
) -> ProductRead:
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != user.organization_id:
        raise NotFoundError("Product not found.")
    return ProductRead.model_validate(product)
