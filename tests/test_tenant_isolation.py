"""Tenant isolation: two organizations, zero leakage.

Cross-tenant reads return **404**, never 403. A 403 would confirm that the id
exists, letting an attacker enumerate another organization's quotes.
"""

from __future__ import annotations

from typing import Any

import pytest_asyncio

from tests.conftest import Api, build_canonical_quote, login, signup


@pytest_asyncio.fixture(loop_scope="session")
async def rival(client) -> dict[str, Any]:
    """A second, fully independent seller tenant with its own catalog."""
    await signup(
        client,
        email="rival.admin@rival.dev",
        full_name="Rival Admin",
        role="ADMIN",
        organization_name="Rival Supplies",
    )
    admin = await login(client, "rival.admin@rival.dev")
    await admin.post(
        "/users",
        json={
            "email": "rival.sales@rival.dev",
            "password": "Password123!",
            "full_name": "Rival Sales",
            "role": "SALES",
        },
        expect=201,
    )
    sales = await login(client, "rival.sales@rival.dev")

    product = (
        await admin.post(
            "/admin/products",
            json={
                "sku": "RIV-1",
                "name": "Rival Widget",
                "category": "HARDWARE",
                "list_price": "500.0000",
                "internal_cost": "250.0000",
                "is_stock_tracked": True,
            },
            expect=201,
        )
    ).json()
    customer = (
        await sales.post(
            "/customers",
            json={
                "customer_organization_name": "Rival Customer Inc",
                "display_name": "Rival Customer Inc",
                "tier": "GOLD",
            },
            expect=201,
        )
    ).json()
    return {
        "admin": admin,
        "sales": sales,
        "product_id": product["id"],
        "customer_profile_id": customer["id"],
    }


async def test_catalogs_are_completely_separate(seeded, rival) -> None:
    ours = (await seeded["sales"].get("/products", expect=200)).json()
    theirs = (await rival["sales"].get("/products", expect=200)).json()

    our_skus = {p["sku"] for p in ours}
    their_skus = {p["sku"] for p in theirs}
    assert "HW-LAPTOP-01" in our_skus
    assert "RIV-1" in their_skus
    assert our_skus & their_skus == set()


async def test_policies_are_separate(seeded, rival) -> None:
    ours = (await seeded["sales"].get("/policies", expect=200)).json()
    theirs = (await rival["sales"].get("/policies", expect=200)).json()
    assert len(ours) == 6
    assert theirs == []


async def test_customers_and_deals_are_separate(seeded, rival) -> None:
    await build_canonical_quote(seeded)
    ours = (await seeded["sales"].get("/deals", expect=200)).json()
    theirs = (await rival["sales"].get("/deals", expect=200)).json()
    assert len(ours) == 1
    assert theirs == []

    our_customers = (await seeded["sales"].get("/customers", expect=200)).json()
    their_customers = (await rival["sales"].get("/customers", expect=200)).json()
    assert {c["display_name"] for c in our_customers} == {"Acme Corporation"}
    assert {c["display_name"] for c in their_customers} == {"Rival Customer Inc"}


async def test_quote_ids_from_another_org_do_not_leak_data(seeded, rival) -> None:
    built = await build_canonical_quote(seeded)
    intruder: Api = rival["sales"]

    for path in (
        f"/quotes/{built['quote']['id']}",
        f"/quote-versions/{built['version_id']}",
        f"/quote-versions/{built['version_id']}/policy-results",
        f"/quote-versions/{built['version_id']}/impact",
        f"/quote-versions/{built['version_id']}/approval",
        f"/quotes/{built['quote']['id']}/recommendations",
        f"/deals/{built['deal']['id']}",
    ):
        response = await intruder.get(path)
        assert response.status_code == 404, f"{path} leaked with {response.status_code}"
        body = response.text
        assert "132710" not in body, "totals leaked across tenants"
        assert "100200" not in body, "cost leaked across tenants"


async def test_cross_tenant_writes_are_rejected(seeded, rival) -> None:
    built = await build_canonical_quote(seeded)
    intruder: Api = rival["sales"]
    line = built["version"]["lines"][0]

    assert (
        await intruder.post(
            f"/quote-versions/{built['version_id']}/lines",
            json={"product_id": rival["product_id"], "quantity": "1"},
        )
    ).status_code == 404
    assert (
        await intruder.patch(
            f"/quote-versions/{built['version_id']}/lines/{line['id']}",
            json={"discount_pct": "99"},
        )
    ).status_code == 404
    assert (
        await intruder.delete(
            f"/quote-versions/{built['version_id']}/lines/{line['id']}"
        )
    ).status_code == 404
    assert (
        await intruder.post(
            f"/quote-versions/{built['version_id']}/submit", json={}
        )
    ).status_code == 404
    assert (
        await intruder.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={"reason": "hijack"},
        )
    ).status_code == 404


async def test_a_deal_cannot_reference_another_orgs_customer(seeded, rival) -> None:
    intruder: Api = rival["sales"]
    response = await intruder.post(
        "/deals",
        json={
            "name": "Poaching Acme",
            "customer_profile_id": seeded["customer_profile_id"],
        },
    )
    assert response.status_code == 404


async def test_a_quote_line_cannot_reference_another_orgs_product(
    seeded, rival
) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    response = await sales.post(
        f"/quote-versions/{built['version_id']}/lines",
        json={"product_id": rival["product_id"], "quantity": "1"},
    )
    assert response.status_code == 404
    assert "not found in your catalog" in response.json()["error"]["message"]


async def test_audit_trails_are_scoped_per_organization(seeded, rival) -> None:
    await build_canonical_quote(seeded)
    ours = (await seeded["sales"].get("/audit/events", expect=200)).json()
    theirs = (await rival["sales"].get("/audit/events", expect=200)).json()
    assert ours
    our_ids = {e["id"] for e in ours}
    their_ids = {e["id"] for e in theirs}
    assert our_ids & their_ids == set()
    assert all("QUOTE_CREATED" != e["event_type"] for e in theirs)


async def test_control_tower_is_scoped_per_organization(seeded, rival) -> None:
    built = await build_canonical_quote(seeded)
    await seeded["sales"].post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )

    ours = (await seeded["sales"].get("/dashboard/control-tower", expect=200)).json()
    theirs = (await rival["sales"].get("/dashboard/control-tower", expect=200)).json()
    assert ours["counts"]["total_open"] >= 1
    assert theirs["counts"]["total_open"] == 0
    assert ours["organization_id"] != theirs["organization_id"]


async def test_deal_health_is_scoped_per_organization(seeded, rival) -> None:
    await build_canonical_quote(seeded)
    ours = (await seeded["sales"].get("/dashboard/deal-health", expect=200)).json()
    theirs = (await rival["sales"].get("/dashboard/deal-health", expect=200)).json()
    assert len(ours["deals"]) == 1
    assert theirs["deals"] == []


async def test_customer_only_sees_quotes_issued_to_their_organization(
    seeded, rival, client
) -> None:
    """Two buyers, each with a quote. Neither may see the other's."""
    sales = seeded["sales"]
    manager, finance = seeded["manager"], seeded["finance"]

    # Our quote, sent to Acme.
    built = await build_canonical_quote(seeded)
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    for approver in (manager, finance):
        inbox = (await approver.get("/approvals/inbox", expect=200)).json()
        for item in inbox:
            await approver.post(
                f"/approvals/{item['approval_request_id']}/approve",
                json={"reason": "ok"},
                expect=200,
            )
    await sales.post(
        f"/quote-versions/{built['version_id']}/send", json={}, expect=200
    )

    # A second buyer belonging to the rival seller.
    rival_customers = (await rival["sales"].get("/customers", expect=200)).json()
    rival_buyer_org = rival_customers[0]["customer_organization_id"]
    await signup(
        client,
        email="buyer@rivalcustomer.dev",
        full_name="Rival Buyer",
        role="CUSTOMER",
        organization_id=rival_buyer_org,
    )
    other_buyer = await login(client, "buyer@rivalcustomer.dev")

    acme = seeded["customer"]
    acme_quotes = (await acme.get("/portal/quotes", expect=200)).json()
    assert len(acme_quotes) == 1
    assert acme_quotes[0]["quote_number"] == built["quote"]["quote_number"]

    other_quotes = (await other_buyer.get("/portal/quotes", expect=200)).json()
    assert other_quotes == []

    # Direct id access is a 404, not a 403.
    response = await other_buyer.get(f"/portal/quotes/{built['quote']['id']}")
    assert response.status_code == 404
    assert "not issued to your organization" in response.text

    for path in (
        f"/portal/quotes/{built['quote']['id']}/messages",
    ):
        assert (await other_buyer.get(path)).status_code == 404
    assert (
        await other_buyer.post(
            f"/portal/quotes/{built['quote']['id']}/messages",
            json={"message_type": "COMMENT", "body": "let me see"},
        )
    ).status_code == 404
    assert (
        await other_buyer.post(
            f"/portal/quotes/{built['quote']['id']}/confirm", json={}
        )
    ).status_code == 404


async def test_orders_are_scoped_per_organization(seeded, rival) -> None:
    intruder: Api = rival["sales"]
    orders = (await intruder.get("/orders", expect=200)).json()
    assert orders == []
    response = await intruder.get(
        "/orders/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404
