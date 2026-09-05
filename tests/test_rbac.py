"""RBAC: every role can do exactly what it should, and nothing more."""

from __future__ import annotations

import pytest

from tests.conftest import build_canonical_quote, page_items

ADMIN_ONLY_WRITES = (
    ("POST", "/admin/products", {
        "sku": "X-1", "name": "X", "category": "HARDWARE",
        "list_price": "1", "internal_cost": "1",
    }),
    ("POST", "/admin/warehouses", {"code": "X", "name": "X"}),
    ("POST", "/admin/policies", {
        "code": "X", "name": "X", "policy_type": "MIN_MARGIN",
        "threshold_value": "5",
    }),
    ("POST", "/admin/seed", None),
    ("POST", "/admin/product-variants", {
        "product_id": "00000000-0000-0000-0000-000000000000",
        "sku": "V", "name": "V",
    }),
    ("POST", "/admin/price-lists", {"code": "P", "name": "P"}),
)


@pytest.mark.parametrize("role", ["sales", "manager", "finance", "ops"])
@pytest.mark.parametrize(("method", "path", "body"), ADMIN_ONLY_WRITES)
async def test_non_admin_roles_cannot_reach_admin_writes(
    seeded, role, method, path, body
) -> None:
    api = seeded[role]
    response = await api.request(method, path, json=body if body is not None else {})
    assert response.status_code == 403, f"{role} reached {path}"
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_admin_can_reach_admin_writes(seeded) -> None:
    admin = seeded["admin"]
    await admin.post(
        "/admin/products",
        json={
            "sku": "HW-DOCK-01",
            "name": "USB-C Dock",
            "category": "HARDWARE",
            "list_price": "180.0000",
            "internal_cost": "90.0000",
        },
        expect=201,
    )
    await admin.post(
        "/admin/warehouses", json={"code": "SOUTH", "name": "South Hub"}, expect=201
    )
    await admin.post(
        "/admin/policies",
        json={
            "code": "PLAT-HW-CEILING",
            "name": "Platinum hardware ceiling",
            "policy_type": "CATEGORY_DISCOUNT_CEILING",
            "customer_tier": "PLATINUM",
            "product_category": "HARDWARE",
            "threshold_value": "20.0000",
            "required_action": "SALES_MANAGER",
        },
        expect=201,
    )


@pytest.mark.parametrize("role", ["sales", "manager", "finance", "ops", "admin"])
async def test_every_internal_role_can_read_the_catalog(seeded, role) -> None:
    api = seeded[role]
    products = page_items((await api.get("/products", expect=200)).json())
    assert len(products) >= 4
    await api.get("/policies", expect=200)
    await api.get("/warehouses", expect=200)
    await api.get("/inventory", expect=200)
    await api.get("/dashboard/control-tower", expect=200)


@pytest.mark.parametrize("role", ["finance", "ops"])
async def test_non_authoring_roles_cannot_create_deals(seeded, role) -> None:
    api = seeded[role]
    response = await api.post(
        "/deals",
        json={"name": "nope", "customer_profile_id": seeded["customer_profile_id"]},
    )
    assert response.status_code == 403


async def test_sales_cannot_use_approval_endpoints(seeded) -> None:
    sales = seeded["sales"]
    assert (await sales.get("/approvals/inbox")).status_code == 403


@pytest.mark.parametrize("role", ["sales", "manager", "ops"])
async def test_only_finance_or_admin_can_issue_invoices(seeded, role) -> None:
    """The restriction is now a declared dependency, not an inline check.

    That makes it visible in the OpenAPI schema, and it reports the permitted
    roles in ``details.allowed_roles`` — which is what a frontend needs in
    order to explain the refusal — rather than embedding them in prose.
    """
    api = seeded[role]
    response = await api.post(
        "/billing/invoices",
        json={"billing_schedule_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 403
    body = response.json()["error"]
    assert body["code"] == "FORBIDDEN"
    assert body["details"]["allowed_roles"] == ["ADMIN", "FINANCE"]
    assert body["details"]["your_role"] == role.upper()


@pytest.mark.parametrize("role", ["sales", "manager", "finance"])
async def test_only_ops_or_admin_can_fulfill(seeded, role) -> None:
    api = seeded[role]
    response = await api.post(
        "/orders/00000000-0000-0000-0000-000000000000/fulfill", json={}
    )
    assert response.status_code == 403
    body = response.json()["error"]
    assert body["code"] == "FORBIDDEN"
    assert body["details"]["allowed_roles"] == ["ADMIN", "OPS"]
    assert body["details"]["your_role"] == role.upper()


@pytest.mark.parametrize("role", ["manager", "finance"])
async def test_only_ops_sales_or_admin_can_allocate(seeded, role) -> None:
    """Allocation is deliberately broader than fulfilment.

    A rep may reserve stock for their own order; only Ops ships it.
    """
    api = seeded[role]
    response = await api.post(
        "/orders/00000000-0000-0000-0000-000000000000/allocate", json={}
    )
    assert response.status_code == 403
    body = response.json()["error"]
    assert body["details"]["allowed_roles"] == ["ADMIN", "OPS", "SALES"]


# --------------------------------------------------- customer portal role
CUSTOMER_FORBIDDEN_INTERNAL = (
    ("GET", "/products"),
    ("GET", "/policies"),
    ("GET", "/warehouses"),
    ("GET", "/inventory"),
    ("GET", "/deals"),
    ("GET", "/users"),
    ("GET", "/dashboard/control-tower"),
    ("GET", "/dashboard/attention-items"),
    ("GET", "/dashboard/deal-health"),
    ("GET", "/audit/events"),
    ("GET", "/billing/schedules"),
    ("GET", "/orders"),
    ("GET", "/approvals/inbox"),
)


@pytest.mark.parametrize(("method", "path"), CUSTOMER_FORBIDDEN_INTERNAL)
async def test_customer_cannot_reach_internal_endpoints(seeded, method, path) -> None:
    customer = seeded["customer"]
    response = await customer.request(method, path)
    assert response.status_code == 403, f"customer reached {path}"
    code = response.json()["error"]["code"]
    assert code in ("PORTAL_USER_FORBIDDEN", "FORBIDDEN")


async def test_customer_cannot_reach_admin_endpoints(seeded) -> None:
    customer = seeded["customer"]
    for method, path, body in ADMIN_ONLY_WRITES:
        response = await customer.request(
            method, path, json=body if body is not None else {}
        )
        assert response.status_code == 403, path


async def test_customer_cannot_create_quotes_or_approve(seeded) -> None:
    customer = seeded["customer"]
    assert (
        await customer.post(
            "/deals",
            json={
                "name": "self-serve",
                "customer_profile_id": seeded["customer_profile_id"],
            },
        )
    ).status_code == 403
    assert (
        await customer.post(
            "/approvals/00000000-0000-0000-0000-000000000000/approve",
            json={"reason": "self approve"},
        )
    ).status_code == 403


async def test_customer_cannot_read_the_internal_quote_view(seeded) -> None:
    """The internal view carries cost and margin — it must be unreachable."""
    built = await build_canonical_quote(seeded)
    customer = seeded["customer"]

    for path in (
        f"/quotes/{built['quote']['id']}",
        f"/quote-versions/{built['version_id']}",
        f"/quote-versions/{built['version_id']}/policy-results",
        f"/quote-versions/{built['version_id']}/impact",
        f"/quote-versions/{built['version_id']}/approval",
    ):
        response = await customer.get(path)
        assert response.status_code == 403, path
        assert response.json()["error"]["code"] == "PORTAL_USER_FORBIDDEN"


async def test_internal_user_cannot_use_portal_endpoints(seeded) -> None:
    """Employees must not read through the redacted view either.

    Otherwise the redacted path becomes a second, less-audited way to see a
    quote, and it stops being obvious which view a caller is entitled to.
    """
    sales = seeded["sales"]
    response = await sales.get("/portal/quotes")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INTERNAL_USER_FORBIDDEN"


async def test_unauthenticated_requests_are_rejected_everywhere(client) -> None:
    protected = [
        ("GET", "/users/me"),
        ("GET", "/products"),
        ("GET", "/deals"),
        ("GET", "/portal/quotes"),
        ("GET", "/approvals/inbox"),
        ("GET", "/dashboard/control-tower"),
        ("POST", "/admin/seed"),
    ]
    for method, path in protected:
        response = await client.request(method, path, json={})
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


async def test_deactivated_user_is_rejected_immediately(seeded, client) -> None:
    """Role/status is re-read per request, so revocation is not token-bound."""
    from sqlalchemy import update

    from app.models.user import User
    from tests.conftest import db_session

    sales = seeded["sales"]
    await sales.get("/users/me", expect=200)

    async with db_session() as s:
        await s.execute(
            update(User)
            .where(User.email == "sales@techsupply.com")
            .values(is_active=False)
        )
        await s.commit()

    response = await sales.get("/users/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "USER_DISABLED"


async def test_role_change_takes_effect_without_a_new_token(seeded) -> None:
    from sqlalchemy import select, update

    from app.models.role import Role
    from app.models.user import User
    from tests.conftest import db_session

    sales = seeded["sales"]
    assert (await sales.get("/approvals/inbox")).status_code == 403

    async with db_session() as s:
        manager_role = (
            await s.execute(select(Role).where(Role.code == "MANAGER"))
        ).scalar_one()
        await s.execute(
            update(User)
            .where(User.email == "sales@techsupply.com")
            .values(role_id=manager_role.id)
        )
        await s.commit()

    # Same token, new permissions.
    assert (await sales.get("/approvals/inbox")).status_code == 200
