"""Audit trail: append-only, complete, and attributable."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.models.audit_event import AuditEvent
from tests.conftest import build_canonical_quote, db_session, page_items

#: Events the canonical P0 flow must leave behind, in order.
REQUIRED_SEQUENCE = (
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
)


async def _full_flow(seeded) -> dict:
    """Run the entire canonical flow so the audit trail is complete."""
    sales, manager, finance = seeded["sales"], seeded["manager"], seeded["finance"]
    ops, customer = seeded["ops"], seeded["customer"]

    built = await build_canonical_quote(seeded)
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    for approver in (manager, finance):
        inbox = (await approver.get("/approvals/inbox", expect=200)).json()
        for item in inbox:
            await approver.post(
                f"/approvals/{item['approval_request_id']}/approve",
                json={"reason": "approved"},
                expect=200,
            )
    await sales.post(
        f"/quote-versions/{built['version_id']}/send", json={}, expect=200
    )

    detail = (
        await customer.get(f"/portal/quotes/{built['quote']['id']}", expect=200)
    ).json()
    laptop = next(
        line
        for line in detail["current_version"]["lines"]
        if "Laptop" in line["description"]
    )
    counter = (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/messages",
            json={
                "message_type": "COUNTER_OFFER",
                "body": "25% or no deal",
                "lines": [
                    {"quote_line_id": laptop["id"], "requested_discount_pct": "25"}
                ],
            },
            expect=201,
        )
    ).json()
    v2_id = counter["new_version_id"]

    for approver in (manager, finance):
        inbox = (await approver.get("/approvals/inbox", expect=200)).json()
        for item in inbox:
            if str(item["quote_version_id"]) == str(v2_id):
                await approver.post(
                    f"/approvals/{item['approval_request_id']}/approve",
                    json={"reason": "re-approved"},
                    expect=200,
                )

    confirm = (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/confirm", json={}, expect=200
        )
    ).json()
    order_id = confirm["order"]["id"]
    await ops.post(f"/orders/{order_id}/allocate", json={}, expect=200)
    await ops.post(f"/orders/{order_id}/fulfill", json={}, expect=200)

    return {"built": built, "v2_id": v2_id, "order_id": order_id}


async def test_the_full_flow_leaves_every_required_event(seeded) -> None:
    await _full_flow(seeded)
    sales = seeded["sales"]
    events = page_items((await sales.get("/audit/events", params={"limit": 200}, expect=200)).json())
    types = [e["event_type"] for e in events]

    for required in REQUIRED_SEQUENCE:
        assert required in types, f"missing audit event: {required}"

    # Events are ordered by a monotonic sequence, not a wall clock.
    sequences = [e["sequence"] for e in events]
    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)


async def test_events_are_ordered_even_within_one_transaction(seeded) -> None:
    """A submit emits several events; ordering must still be unambiguous."""
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    events = page_items((await sales.get("/audit/events", params={"limit": 200}, expect=200)).json())
    submitted = next(e for e in events if e["event_type"] == "QUOTE_SUBMITTED")
    evaluated = next(e for e in events if e["event_type"] == "POLICY_EVALUATED")
    requested = next(e for e in events if e["event_type"] == "APPROVAL_REQUESTED")
    assert submitted["sequence"] < evaluated["sequence"] < requested["sequence"]


async def test_every_event_records_the_actor(seeded) -> None:
    await _full_flow(seeded)
    sales = seeded["sales"]
    events = page_items((await sales.get("/audit/events", params={"limit": 200}, expect=200)).json())

    actors: dict[str, set[str]] = {}
    for event in events:
        assert event["occurred_at"]
        assert event["entity_type"]
        if event["event_type"] in ("ATTENTION_ITEM_CREATED", "ATTENTION_ITEM_RESOLVED"):
            continue
        assert event["actor_email"], f"{event['event_type']} has no actor"
        assert event["actor_role"], f"{event['event_type']} has no actor role"
        actors.setdefault(event["event_type"], set()).add(event["actor_email"])

    assert actors["QUOTE_SUBMITTED"] == {"sales@techsupply.com"}
    assert actors["CUSTOMER_COUNTERED"] == {"customer@acme.com"}
    assert actors["QUOTE_CONFIRMED"] == {"customer@acme.com"}
    assert actors["APPROVAL_GRANTED"] == {
        "manager@techsupply.com",
        "finance@techsupply.com",
    }


async def test_approval_events_capture_the_numbers_at_decision_time(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales, manager = seeded["sales"], seeded["manager"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    inbox = (await manager.get("/approvals/inbox", expect=200)).json()
    await manager.post(
        f"/approvals/{inbox[0]['approval_request_id']}/approve",
        json={"reason": "Volume justifies it."},
        expect=200,
    )

    events = (
        await sales.get(
            "/audit/events", params={"event_type": "APPROVAL_GRANTED"}, expect=200
        )
    ).json()
    payload = events[0]["payload"]
    assert payload["reason"] == "Volume justifies it."
    assert payload["level"] == "SALES_MANAGER"
    financials = payload["financials_at_decision"]
    assert financials["total_revenue"] == "132710.00"
    assert financials["margin_pct"] == "24.4970"
    assert financials["total_cost"] == "100200.00"


async def test_stale_approval_event_explains_the_cause(seeded) -> None:
    await _full_flow(seeded)
    sales = seeded["sales"]
    events = (
        await sales.get(
            "/audit/events",
            params={"event_type": "APPROVAL_MARKED_STALE"},
            expect=200,
        )
    ).json()
    assert len(events) == 1
    payload = events[0]["payload"]
    assert payload["previous_decision"] == "APPROVED"
    assert "no longer valid" in payload["reason"]
    assert payload["new_version_number"] == 2
    assert payload["material_changes"]
    assert any(
        c["field"] == "discount_pct" for c in payload["material_changes"]
    )


async def test_material_change_event_lists_every_change(seeded) -> None:
    await _full_flow(seeded)
    sales = seeded["sales"]
    events = (
        await sales.get(
            "/audit/events",
            params={"event_type": "MATERIAL_CHANGE_DETECTED"},
            expect=200,
        )
    ).json()
    assert events
    payload = events[-1]["payload"]
    assert payload["material_change_count"] >= 1
    fields = {c["field"] for c in payload["changes"]}
    assert "discount_pct" in fields
    for change in payload["changes"]:
        assert change["reason"]
        assert change["severity"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


async def test_order_and_billing_events_carry_the_totals(seeded) -> None:
    await _full_flow(seeded)
    sales = seeded["sales"]

    order_events = (
        await sales.get(
            "/audit/events", params={"event_type": "ORDER_CREATED"}, expect=200
        )
    ).json()
    assert len(order_events) == 1
    payload = order_events[0]["payload"]
    assert payload["order_number"].startswith("SO-")
    assert Decimal(payload["total_amount"]) == Decimal("124310.00")
    assert Decimal(payload["one_time_amount"]) == Decimal("124010.00")
    assert Decimal(payload["recurring_amount"]) == Decimal("300.00")

    billing_events = (
        await sales.get(
            "/audit/events", params={"event_type": "BILLING_SCHEDULED"}, expect=200
        )
    ).json()
    payload = billing_events[0]["payload"]
    assert payload["schedule_count"] == 4
    assert Decimal(payload["one_time_total"]) == Decimal("124010.00")
    assert Decimal(payload["recurring_total"]) == Decimal("300.00")
    assert len(payload["schedules"]) == 4


async def test_allocation_event_records_the_warehouse_split(seeded) -> None:
    await _full_flow(seeded)
    sales = seeded["sales"]
    events = (
        await sales.get(
            "/audit/events",
            params={"event_type": "INVENTORY_ALLOCATED"},
            expect=200,
        )
    ).json()
    payload = events[0]["payload"]
    assert payload["fully_allocated"] is True
    assert payload["shipment_count"] == 2

    # Lines are ordered by product_id (a UUID) because allocation locks rows in
    # that order to avoid deadlocks — so select the line by name, not position.
    laptop = next(
        line for line in payload["lines"] if line["product_name"] == "Business Laptop"
    )
    quantities = {
        s["warehouse_name"]: Decimal(s["quantity"]) for s in laptop["splits"]
    }
    assert quantities == {
        "Main Warehouse": Decimal("60"),
        "East Depot": Decimal("40"),
    }

    monitor = next(
        line for line in payload["lines"] if line["product_name"] == '27" Monitor'
    )
    assert Decimal(monitor["quantity_allocated"]) == Decimal("100")


async def test_money_in_audit_payloads_is_stored_as_strings(seeded) -> None:
    """A float in JSONB would silently corrupt the record of a decision."""
    await _full_flow(seeded)
    async with db_session() as s:
        events = list((await s.execute(select(AuditEvent))).scalars())

    def assert_no_floats(node: object, path: str) -> None:
        if isinstance(node, float):
            raise AssertionError(f"float found in audit payload at {path}: {node}")
        if isinstance(node, dict):
            for key, value in node.items():
                assert_no_floats(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                assert_no_floats(value, f"{path}[{index}]")

    assert events
    for event in events:
        assert_no_floats(event.payload, event.event_type)


async def test_quote_timeline_stitches_the_whole_story(seeded) -> None:
    result = await _full_flow(seeded)
    sales = seeded["sales"]
    timeline = (
        await sales.get(
            f"/audit/quotes/{result['built']['quote']['id']}/timeline", expect=200
        )
    ).json()
    types = [e["event_type"] for e in timeline]

    for required in (
        "QUOTE_CREATED",
        "QUOTE_SUBMITTED",
        "QUOTE_APPROVED",
        "QUOTE_SENT",
        "CUSTOMER_COUNTERED",
        "APPROVAL_MARKED_STALE",
        "QUOTE_CONFIRMED",
        "ORDER_CREATED",
    ):
        assert required in types, f"{required} missing from the quote timeline"

    sequences = [e["sequence"] for e in timeline]
    assert sequences == sorted(sequences)


async def test_audit_events_are_never_updated(seeded) -> None:
    """The table has no updated_at because nothing may rewrite history."""
    from app.models.audit_event import AuditEvent as Model

    columns = set(Model.__table__.columns.keys())
    assert "updated_at" not in columns
    assert "created_at" in columns
    assert "occurred_at" in columns


async def test_login_and_signup_are_audited(seeded, client) -> None:
    from tests.conftest import login, signup

    await signup(
        client,
        email="audited@newco.dev",
        full_name="Audited",
        role="ADMIN",
        organization_name="Audited Co",
    )
    api = await login(client, "audited@newco.dev")
    events = page_items((await api.get("/audit/events", expect=200)).json())
    types = {e["event_type"] for e in events}
    assert "USER_SIGNED_UP" in types
    assert "USER_LOGGED_IN" in types


async def test_rejection_is_audited_with_its_reason(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales, manager = seeded["sales"], seeded["manager"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    inbox = (await manager.get("/approvals/inbox", expect=200)).json()
    await manager.post(
        f"/approvals/{inbox[0]['approval_request_id']}/reject",
        json={"reason": "Margin story does not hold up."},
        expect=200,
    )
    events = (
        await sales.get(
            "/audit/events", params={"event_type": "APPROVAL_REJECTED"}, expect=200
        )
    ).json()
    assert len(events) == 1
    assert events[0]["payload"]["reason"] == "Margin story does not hold up."
    assert events[0]["actor_email"] == "manager@techsupply.com"


async def test_negotiation_messages_are_audited(seeded) -> None:
    await _full_flow(seeded)
    sales = seeded["sales"]
    events = (
        await sales.get(
            "/audit/events", params={"event_type": "CUSTOMER_COUNTERED"}, expect=200
        )
    ).json()
    assert len(events) == 1
    payload = events[0]["payload"]
    assert payload["customer"] == "Acme Corporation"
    assert payload["body"] == "25% or no deal"
    assert payload["requested_lines"][0]["requested_discount_pct"] == "25.0000"
