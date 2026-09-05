"""HTTP layer. Routers validate, delegate to services, and own the commit."""

from __future__ import annotations

from fastapi import APIRouter

from app.routers import (
    admin,
    approvals,
    auth,
    billing,
    customers,
    dashboard,
    deals,
    inventory,
    negotiations,
    orders,
    policies,
    products,
    quotes,
    users,
)

#: Registration order controls the tag order in the OpenAPI docs.
ALL_ROUTERS: tuple[APIRouter, ...] = (
    auth.router,
    users.router,
    admin.router,
    products.router,
    policies.router,
    inventory.router,
    customers.router,
    deals.router,
    quotes.router,
    approvals.router,
    negotiations.router,
    orders.router,
    billing.router,
    dashboard.router,
)

__all__ = ["ALL_ROUTERS"]
