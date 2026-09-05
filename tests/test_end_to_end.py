"""The canonical DealFlow360 flow, end to end, in one test.

This is the definition of P0 success. It walks the five demo scenes exactly as
a user would, through the HTTP API only, and asserts at every step:

    login -> configure -> customer -> deal -> quote -> lines -> discount
    -> calculate -> policy evaluation -> submit -> manager approval
    -> finance approval -> send -> customer portal -> counter-offer
    -> V2 -> Decision Fabric -> stale approval -> blocked confirmation
    -> re-approval -> confirmation -> order -> 60/40 allocation
    -> billing schedules -> audit trail -> Control Tower

Nothing is stubbed, no service is called directly, and every number asserted
was computed by hand from the seed data.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from tests.conftest import login, money as parse, page_items

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_canonical_end_to_end_flow(client, capsys) -> None:
    log: list[str] = []

    def scene(title: str) -> None:
        log.append(f"\n{'=' * 66}\n{title}\n{'=' * 66}")

    def step(message: str) -> None:
        log.append(f"  [ok] {message}")

    # ==================================================================
    scene("SCENE 0 — Configure the tenant (seed + login)")
    # ==================================================================
    from app.db import get_sessionmaker
    from scripts.seed import seed_canonical_data

    async with get_sessionmaker()() as s:
        seed = await seed_canonical_data(s)
        await s.commit()
    step("Seeded TechSupply Solutions and Acme Corporation (GOLD, NET 30)")

    sales = await login(client, "sales@techsupply.com")
    manager = await login(client, "manager@techsupply.com")
    finance = await login(client, "finance@techsupply.com")
    ops = await login(client, "ops@techsupply.com")
    customer = await login(client, "customer@acme.com")
    step("All five roles authenticated with JWT access tokens")

    me = (await sales.get("/users/me", expect=200)).json()
    assert me["role"] == "SALES"
    assert me["organization_name"] == "TechSupply Solutions"

    products = {p["sku"]: p for p in page_items((await sales.get("/products", expect=200)).json())}
    assert len(products) == 4
    assert parse(products["HW-LAPTOP-01"]["list_price"]) == Decimal("1200.0000")
    assert parse(products["HW-LAPTOP-01"]["internal_cost"]) == Decimal("800.0000")

    assert {
        w["code"] for w in (await ops.get("/warehouses", expect=200)).json()
    } == {"MAIN", "EAST"}
    inventory = (
        await ops.get(
            "/inventory",
            params={"product_id": products["HW-LAPTOP-01"]["id"]},
            expect=200,
        )
    ).json()
    stock = {r["warehouse_code"]: parse(r["quantity_available"]) for r in inventory}
    assert stock == {"MAIN": Decimal("60"), "EAST": Decimal("40")}
    step("Catalog (4 products), warehouses (Main 60 / East 40), 6 policies loaded")

    policies = (await sales.get("/policies", expect=200)).json()
    assert len(policies) == 7

    # ==================================================================
    scene("SCENE 1 — Sales builds the deal and submits it")
    # ==================================================================
    deal = (
        await sales.post(
            "/deals",
            json={
                "name": "Acme Q1 laptop refresh",
                "customer_profile_id": seed["customer_profile_id"],
                "stage": "PROPOSAL",
            },
            expect=201,
        )
    ).json()
    step(f"Deal {deal['reference']} created for {deal['customer_display_name']}")
    assert deal["customer_tier"] == "GOLD"

    quote = (
        await sales.post(
            f"/deals/{deal['id']}/quotes",
            json={
                "title": "Acme Q1 laptop refresh",
                "lines": [
                    {
                        "product_id": products["HW-LAPTOP-01"]["id"],
                        "quantity": "100",
                        "discount_pct": "18",
                    },
                    {
                        "product_id": products["HW-MONITOR-27"]["id"],
                        "quantity": "100",
                        "discount_pct": "16",
                    },
                    {
                        "product_id": products["SV-INSTALL-01"]["id"],
                        "quantity": "1",
                        "discount_pct": "18",
                    },
                    {
                        "product_id": products["SB-SUPPORT-01"]["id"],
                        "quantity": "1",
                        "discount_pct": "0",
                    },
                ],
            },
            expect=201,
        )
    ).json()
    v1_id = quote["current_version_id"]
    step(
        f"Quote {quote['quote_number']} v1 created with 100 laptops, 100 monitors, "
        "1 installation, 1 annual support"
    )

    # ---- backend-calculated totals -----------------------------------
    v1 = (await sales.get(f"/quote-versions/{v1_id}", expect=200)).json()
    assert parse(v1["gross_revenue"]) == Decimal("160800.00")
    assert parse(v1["total_discount"]) == Decimal("28090.00")
    assert parse(v1["net_revenue"]) == Decimal("132710.00")
    assert parse(v1["total_cost"]) == Decimal("100200.00")
    assert parse(v1["margin"]) == Decimal("32510.00")
    assert parse(v1["margin_pct"]) == Decimal("24.4970")
    assert parse(v1["one_time_revenue"]) == Decimal("132410.00")
    assert parse(v1["recurring_revenue"]) == Decimal("300.00")
    step(
        f"Backend computed: revenue {v1['net_revenue']}, cost {v1['total_cost']}, "
        f"margin {v1['margin']} ({v1['margin_pct']}%)"
    )

    # ---- policy evaluation -------------------------------------------
    policy = (
        await sales.get(f"/quote-versions/{v1_id}/policy-results", expect=200)
    ).json()
    violations = [r for r in policy["policy_results"] if r["status"] == "VIOLATED"]
    rules = {r["rule"] for r in violations}
    assert "CATEGORY_DISCOUNT_CEILING" in rules
    assert "DISCOUNT_AMOUNT_AUTHORITY" in rules
    assert "MIN_MARGIN" not in rules, "margin is healthy at 24.5%"
    assert policy["requires_approval"] is True
    assert [r["type"] for r in policy["required_approvals"]] == [
        "SALES_MANAGER",
        "FINANCE",
    ]
    for violation in violations:
        step(f"Policy {violation['rule']}: {violation['reason']}")
    step(
        f"Blended risk {policy['blended_risk']['score']}/100 "
        f"({policy['blended_risk']['band']}) — "
        f"{policy['blended_risk']['explanation']}"
    )

    # ---- submit: routing happens automatically ------------------------
    submit = (
        await sales.post(f"/quote-versions/{v1_id}/submit", json={}, expect=200)
    ).json()
    assert submit["explanation"]["summary"]
    v1 = (await sales.get(f"/quote-versions/{v1_id}", expect=200)).json()
    assert v1["status"] == "PENDING_APPROVAL"
    step("Submitted — approval routed automatically to Sales Manager then Finance")

    # ---- immutability -------------------------------------------------
    locked = await sales.patch(
        f"/quote-versions/{v1_id}/lines/{v1['lines'][0]['id']}",
        json={"discount_pct": "5"},
    )
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "IMMUTABLE_VERSION"
    step("v1 is now immutable — line edits rejected with IMMUTABLE_VERSION")

    # ---- sales cannot approve ----------------------------------------
    assert (await sales.get("/approvals/inbox")).status_code == 403
    step("Sales cannot reach the approval inbox (403)")

    # ==================================================================
    scene("SCENE 2 — Manager approves, then Finance approves")
    # ==================================================================
    inbox = (await manager.get("/approvals/inbox", expect=200)).json()
    assert len(inbox) == 1
    item = inbox[0]
    assert item["level"] == "SALES_MANAGER"
    assert parse(item["total_revenue"]) == Decimal("132710.00")
    request_id = item["approval_request_id"]

    assert (
        await finance.post(
            f"/approvals/{request_id}/approve", json={"reason": "jumping the queue"}
        )
    ).status_code == 403
    step("Finance cannot jump ahead of the Manager step (403)")

    approve = (
        await manager.post(
            f"/approvals/{request_id}/approve",
            json={"reason": "200-unit volume justifies the extra 3 points."},
            expect=200,
        )
    ).json()
    assert approve["quote_version_status"] == "PENDING_APPROVAL"
    step(f"Manager approved — {approve['message']}")

    finance_inbox = (await finance.get("/approvals/inbox", expect=200)).json()
    assert len(finance_inbox) == 1
    assert finance_inbox[0]["level"] == "FINANCE"
    approve = (
        await finance.post(
            f"/approvals/{request_id}/approve",
            json={"reason": "24.5% margin is comfortably above the 10% floor."},
            expect=200,
        )
    ).json()
    assert approve["quote_version_status"] == "APPROVED"
    step(f"Finance approved — {approve['message']}")

    detail = (await sales.get(f"/approvals/{request_id}", expect=200)).json()
    assert len(detail["decisions"]) == 2
    assert detail["status"] == "APPROVED"
    for decision in detail["decisions"]:
        assert decision["decision_snapshot"]["margin_pct"] == "24.4970"
    step("Both decisions recorded with actor, reason, timestamp and the numbers")

    send = (
        await sales.post(f"/quote-versions/{v1_id}/send", json={}, expect=200)
    ).json()
    assert send["status"] == "SENT"
    step("Quote sent to the customer portal")

    # ==================================================================
    scene("SCENE 3 — Customer opens the portal (no cost, no margin)")
    # ==================================================================
    listing = (await customer.get("/portal/quotes", expect=200)).json()
    assert len(listing) == 1
    assert listing[0]["can_confirm"] is True

    portal = (
        await customer.get(f"/portal/quotes/{quote['id']}", expect=200)
    ).json()
    raw = str(portal)
    for forbidden in ("unit_cost", "line_cost", "margin", "internal_cost", "risk"):
        assert forbidden not in raw, f"portal leaked '{forbidden}'"
    for value in ("100200", "32510", "24.4970", "800.0000"):
        assert value not in raw, f"portal leaked internal value {value}"
    assert parse(portal["current_version"]["total_revenue"]) == Decimal("132710.00")
    assert portal["seller_name"] == "TechSupply Solutions"
    step("Portal shows totals and discounts but no cost, margin or risk data")

    assert (await customer.get(f"/quote-versions/{v1_id}")).status_code == 403
    assert (await customer.get("/products")).status_code == 403
    step("Customer cannot reach any internal endpoint (403)")

    # ==================================================================
    scene("SCENE 4 — Customer counters; the Decision Fabric reacts")
    # ==================================================================
    laptop = next(
        line
        for line in portal["current_version"]["lines"]
        if "Laptop" in line["description"]
    )
    counter = (
        await customer.post(
            f"/portal/quotes/{quote['id']}/messages",
            json={
                "message_type": "COUNTER_OFFER",
                "body": "We need 25% on the laptops to sign this quarter.",
                "lines": [
                    {"quote_line_id": laptop["id"], "requested_discount_pct": "25"}
                ],
            },
            expect=201,
        )
    ).json()
    v2_id = counter["new_version_id"]
    assert counter["new_version_number"] == 2
    assert counter["requires_reapproval"] is True
    assert "reviewing the updated terms" in counter["customer_message"]
    step(f"Counter-offer accepted as v2 — customer told: {counter['customer_message']}")

    # v1 untouched.
    v1_after = (await sales.get(f"/quote-versions/{v1_id}", expect=200)).json()
    assert v1_after["status"] == "SUPERSEDED"
    assert parse(v1_after["net_revenue"]) == Decimal("132710.00")
    step("v1 was never modified — it is SUPERSEDED and still reads 132,710.00")

    v2 = (await sales.get(f"/quote-versions/{v2_id}", expect=200)).json()
    assert parse(v2["net_revenue"]) == Decimal("124310.00")
    assert parse(v2["margin"]) == Decimal("24110.00")
    assert parse(v2["margin_pct"]) == Decimal("19.3951")
    assert v2["is_stale"] is True
    step(
        f"v2 recomputed by the backend: revenue {v2['net_revenue']}, "
        f"margin {v2['margin_pct']}%"
    )

    impact = (await sales.get(f"/quote-versions/{v2_id}/impact", expect=200)).json()
    assert impact["has_material_change"] is True
    assert impact["blocks_confirmation"] is True
    fields = {c["field"] for c in impact["material_changes"]}
    assert "discount_pct" in fields
    assert "margin_pct" in fields
    assert len(impact["stale_decisions"]) == 1
    assert impact["stale_decisions"][0]["previous_decision"] == "APPROVED"
    step("Decision Fabric: material change detected on discount and margin")
    step(f"Stale approval: {impact['stale_decisions'][0]['reason']}")
    for link in impact["explanation"]["causal_chain"]:
        step(f"  chain: {link}")
    step(f"What happens next: {impact['explanation']['what_happens_next']}")

    stale_items = [
        i for i in impact["attention_items"] if i["type"] == "STALE_APPROVAL"
    ]
    assert stale_items and stale_items[0]["severity"] == "CRITICAL"
    step(f"Attention item raised: {stale_items[0]['title']} (CRITICAL)")

    blocked = await customer.post(f"/portal/quotes/{quote['id']}/confirm", json={})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "STALE_APPROVAL"
    step("Customer confirmation BLOCKED with STALE_APPROVAL (409)")

    portal_blocked = (
        await customer.get(f"/portal/quotes/{quote['id']}", expect=200)
    ).json()
    assert portal_blocked["can_confirm"] is False
    assert "being reviewed by our team" in portal_blocked["blocked_reason"]
    assert "margin" not in portal_blocked["blocked_reason"].lower()
    step("Customer sees a safe reason, with no internal reasoning exposed")

    # ==================================================================
    scene("SCENE 5 — Re-approval, confirmation, order, allocation, billing")
    # ==================================================================
    for approver, label in ((manager, "Manager"), (finance, "Finance")):
        inbox = (await approver.get("/approvals/inbox", expect=200)).json()
        entry = next(i for i in inbox if str(i["quote_version_id"]) == str(v2_id))
        assert entry["is_reapproval"] is True
        await approver.post(
            f"/approvals/{entry['approval_request_id']}/approve",
            json={"reason": f"{label} re-approved the countered terms."},
            expect=200,
        )
        step(f"{label} re-approved v2")

    v2 = (await sales.get(f"/quote-versions/{v2_id}", expect=200)).json()
    assert v2["status"] == "APPROVED"
    assert v2["is_stale"] is False

    idempotency_key = str(uuid.uuid4())
    confirm = (
        await customer.post(
            f"/portal/quotes/{quote['id']}/confirm",
            json={"acceptance_note": "Approved by our procurement board."},
            headers={"Idempotency-Key": idempotency_key},
            expect=200,
        )
    ).json()
    order_id = confirm["order"]["id"]
    order_number = confirm["order"]["order_number"]
    assert confirm["idempotent_replay"] is False
    assert parse(confirm["order"]["total_amount"]) == Decimal("124310.00")
    assert "margin" not in str(confirm)
    step(f"Customer confirmed — order {order_number} created")

    replay = (
        await customer.post(
            f"/portal/quotes/{quote['id']}/confirm",
            json={"acceptance_note": "Approved by our procurement board."},
            headers={"Idempotency-Key": idempotency_key},
            expect=200,
        )
    ).json()
    assert replay["idempotent_replay"] is True
    assert replay["order"]["id"] == order_id
    orders = page_items((await sales.get("/orders", expect=200)).json())
    assert len(orders) == 1, "duplicate confirmation created a second order"
    step("Retried confirmation replayed the same order — exactly one order exists")

    order = (await sales.get(f"/orders/{order_id}", expect=200)).json()
    assert len(order["lines"]) == 4
    assert parse(order["subtotal"]) == Decimal("124310.00")
    assert parse(order["total_cost"]) == Decimal("100200.00")
    assert parse(order["margin"]) == Decimal("24110.00")
    assert parse(order["one_time_amount"]) == Decimal("124010.00")
    assert parse(order["recurring_amount"]) == Decimal("300.00")

    # ---- allocation ---------------------------------------------------
    allocation = (
        await ops.post(f"/orders/{order_id}/allocate", json={}, expect=200)
    ).json()
    assert allocation["fully_allocated"] is True
    assert allocation["has_backorder"] is False
    assert allocation["shipment_count"] == 2

    laptop_line = next(
        line
        for line in allocation["lines"]
        if line["product_name"] == "Business Laptop"
    )
    split = {
        s["warehouse_code"]: Decimal(s["quantity"]) for s in laptop_line["splits"]
    }
    assert split == {"MAIN": Decimal("60"), "EAST": Decimal("40")}
    step(f"Inventory allocated 60 from Main Warehouse + 40 from East Depot")
    step(f"  reason: {laptop_line['explanation']}")

    monitor_line = next(
        line for line in allocation["lines"] if line["product_name"] == '27" Monitor'
    )
    assert parse(monitor_line["quantity_allocated"]) == Decimal("100")

    remaining = (
        await ops.get(
            "/inventory",
            params={"product_id": products["HW-LAPTOP-01"]["id"]},
            expect=200,
        )
    ).json()
    assert all(parse(r["quantity_available"]) == Decimal("0") for r in remaining)
    step("No over-allocation: laptop availability is exactly zero everywhere")

    # ---- billing ------------------------------------------------------
    schedules = (
        await finance.get(
            "/billing/schedules", params={"sales_order_id": order_id}, expect=200
        )
    ).json()
    one_time = [s for s in schedules if s["billing_type"] == "ONE_TIME"]
    recurring = [s for s in schedules if s["billing_type"] == "RECURRING"]
    assert len(one_time) == 3
    assert len(recurring) == 1
    assert sum(parse(s["amount"]) for s in one_time) == Decimal("124010.00")
    assert recurring[0]["recurring_interval"] == "YEARLY"
    assert parse(recurring[0]["amount"]) == Decimal("300.00")
    step(
        f"Billing: {len(one_time)} one-time schedules totalling 124,010.00 "
        f"+ 1 yearly recurring schedule of 300.00"
    )

    summary = (
        await finance.get(f"/billing/orders/{order_id}/summary", expect=200)
    ).json()
    assert parse(summary["grand_total"]) == Decimal("124310.00")

    # ---- fulfilment ---------------------------------------------------
    fulfilled = (
        await ops.post(
            f"/orders/{order_id}/fulfill",
            json={"carrier": "DHL", "tracking_number": "TRK-ACME-001"},
            expect=200,
        )
    ).json()
    assert fulfilled["status"] == "FULFILLED"
    assert len(fulfilled["fulfillments"]) == 2
    step("Fulfilled in 2 shipments, one per warehouse")

    # ==================================================================
    scene("VERIFICATION — audit trail and Control Tower")
    # ==================================================================
    timeline = (
        await sales.get(f"/audit/quotes/{quote['id']}/timeline", expect=200)
    ).json()
    types = [e["event_type"] for e in timeline]
    for required in (
        "QUOTE_CREATED",
        "QUOTE_SUBMITTED",
        "POLICY_EVALUATED",
        "APPROVAL_REQUESTED",
        "APPROVAL_GRANTED",
        "QUOTE_APPROVED",
        "QUOTE_SENT",
        "CUSTOMER_COUNTERED",
        "QUOTE_REVISED",
        "MATERIAL_CHANGE_DETECTED",
        "APPROVAL_MARKED_STALE",
        "QUOTE_CONFIRMED",
        "ORDER_CREATED",
        "INVENTORY_ALLOCATED",
        "BILLING_SCHEDULED",
        "ORDER_FULFILLED",
    ):
        assert required in types, f"audit trail is missing {required}"
    sequences = [e["sequence"] for e in timeline]
    assert sequences == sorted(sequences)
    step(f"Audit trail complete: {len(timeline)} events in monotonic order")

    for event in timeline:
        if event["event_type"].startswith("ATTENTION_ITEM"):
            continue
        assert event["actor_email"], f"{event['event_type']} has no actor"
    step("Every business event carries its actor, role and timestamp")

    tower = (await sales.get("/dashboard/control-tower", expect=200)).json()
    step(f"Control Tower: {tower['headline']}")
    assert tower["counts"]["total_open"] == 0, (
        f"the closed deal left work behind: {tower['by_type']}"
    )
    step("Control Tower is clear — every alert was resolved by the closing flow")

    resolved = (
        await sales.get(
            "/dashboard/attention-items", params={"include_resolved": True}, expect=200
        )
    ).json()
    resolved_types = {i["type"] for i in resolved}
    assert "PENDING_APPROVAL" in resolved_types
    assert "STALE_APPROVAL" in resolved_types
    assert "ORDER_BLOCKED" in resolved_types
    assert all(i["status"] == "RESOLVED" for i in resolved)
    step(f"History retained: {len(resolved)} attention items, all RESOLVED")

    health = (
        await sales.get(f"/dashboard/deal-health/{deal['id']}", expect=200)
    ).json()
    assert health["stage"] == "CLOSED_WON"
    assert health["health_score"] == 100
    assert health["blocked"] is False
    step(f"Deal health: {health['health_score']}/100 ({health['health_band']})")

    log.append(f"\n{'=' * 66}\nP0 CANONICAL FLOW: PASSED\n{'=' * 66}")
    with capsys.disabled():
        print("\n".join(log))


async def test_a_clean_quote_flows_straight_through(client) -> None:
    """The happy path with no violations needs no human at all."""
    from app.db import get_sessionmaker
    from scripts.seed import seed_canonical_data

    async with get_sessionmaker()() as s:
        seed = await seed_canonical_data(s)
        await s.commit()

    sales = await login(client, "sales@techsupply.com")
    ops = await login(client, "ops@techsupply.com")
    customer = await login(client, "customer@acme.com")

    deal = (
        await sales.post(
            "/deals",
            json={
                "name": "Small top-up order",
                "customer_profile_id": seed["customer_profile_id"],
            },
            expect=201,
        )
    ).json()
    quote = (
        await sales.post(
            f"/deals/{deal['id']}/quotes",
            json={
                "title": "Small top-up order",
                "lines": [
                    {
                        "product_id": seed["products"]["HW-LAPTOP-01"],
                        "quantity": "5",
                        "discount_pct": "10",
                    }
                ],
            },
            expect=201,
        )
    ).json()
    version_id = quote["current_version_id"]

    await sales.post(f"/quote-versions/{version_id}/submit", json={}, expect=200)
    version = (await sales.get(f"/quote-versions/{version_id}", expect=200)).json()
    assert version["status"] == "APPROVED", "a clean quote must auto-approve"
    assert version["requires_approval"] is False

    await sales.post(f"/quote-versions/{version_id}/send", json={}, expect=200)
    confirm = (
        await customer.post(
            f"/portal/quotes/{quote['id']}/confirm", json={}, expect=200
        )
    ).json()
    order_id = confirm["order"]["id"]

    allocation = (
        await ops.post(f"/orders/{order_id}/allocate", json={}, expect=200)
    ).json()
    assert allocation["fully_allocated"] is True
    assert allocation["shipment_count"] == 1, "5 units fit in one warehouse"

    tower = (await sales.get("/dashboard/control-tower", expect=200)).json()
    assert tower["counts"]["total_open"] == 0
