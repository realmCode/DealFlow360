"""Customer portal: redaction, counter-offers, and the confirmation block."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from tests.conftest import Api, build_canonical_quote, money as parse

#: Field names that must never appear anywhere in a portal response.
FORBIDDEN_KEYS = (
    "unit_cost",
    "internal_cost",
    "line_cost",
    "total_cost",
    "cost",
    "margin",
    "margin_pct",
    "line_margin",
    "line_margin_pct",
    "blended_risk_score",
    "risk_band",
    "policy_results",
    "required_approvals",
    "stale_reason",
    "requires_approval",
    "policy_summary",
    "decision_snapshot",
)


def _assert_no_internal_data(payload: object, *, context: str) -> None:
    """Walk a decoded response and assert no internal key or value leaked."""
    raw = json.dumps(payload)

    def walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                assert key not in FORBIDDEN_KEYS, (
                    f"{context}: leaked internal field '{key}' at {path}"
                )
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(payload, context)

    # Canonical internal figures for the demo quote — none may appear.
    for internal_value in ("100200.00", "32510.00", "24.4970", "800.0000"):
        assert internal_value not in raw, (
            f"{context}: internal value {internal_value} leaked"
        )


async def _send_to_customer(seeded, version_id: str) -> None:
    sales, manager, finance = seeded["sales"], seeded["manager"], seeded["finance"]
    await sales.post(f"/quote-versions/{version_id}/submit", json={}, expect=200)
    for approver in (manager, finance):
        inbox = (await approver.get("/approvals/inbox", expect=200)).json()
        for item in inbox:
            if str(item["quote_version_id"]) == str(version_id):
                await approver.post(
                    f"/approvals/{item['approval_request_id']}/approve",
                    json={"reason": "approved"},
                    expect=200,
                )
    await sales.post(f"/quote-versions/{version_id}/send", json={}, expect=200)


@pytest.fixture
def customer(seeded) -> Api:
    return seeded["customer"]


# ------------------------------------------------------------- visibility
async def test_customer_sees_nothing_before_the_quote_is_sent(
    seeded, customer
) -> None:
    built = await build_canonical_quote(seeded)
    assert (await customer.get("/portal/quotes", expect=200)).json() == []
    response = await customer.get(f"/portal/quotes/{built['quote']['id']}")
    assert response.status_code == 404


async def test_customer_sees_the_quote_once_sent(seeded, customer) -> None:
    built = await build_canonical_quote(seeded)
    await _send_to_customer(seeded, built["version_id"])

    listing = (await customer.get("/portal/quotes", expect=200)).json()
    assert len(listing) == 1
    entry = listing[0]
    assert entry["quote_number"] == built["quote"]["quote_number"]
    assert entry["status"] == "SENT"
    assert entry["awaiting_customer"] is True
    assert entry["can_confirm"] is True
    assert entry["blocked_reason"] is None
    assert parse(entry["total_revenue"]) == Decimal("132710.00")
    _assert_no_internal_data(listing, context="GET /portal/quotes")


async def test_portal_quote_detail_is_fully_redacted(seeded, customer) -> None:
    built = await build_canonical_quote(seeded)
    await _send_to_customer(seeded, built["version_id"])

    detail = (
        await customer.get(f"/portal/quotes/{built['quote']['id']}", expect=200)
    ).json()
    _assert_no_internal_data(detail, context="GET /portal/quotes/{id}")

    version = detail["current_version"]
    # What they *should* see.
    assert parse(version["gross_revenue"]) == Decimal("160800.00")
    assert parse(version["total_discount"]) == Decimal("28090.00")
    assert parse(version["total_revenue"]) == Decimal("132710.00")
    assert parse(version["one_time_revenue"]) == Decimal("132410.00")
    assert parse(version["recurring_revenue"]) == Decimal("300.00")
    assert detail["seller_name"] == "TechSupply Solutions"
    assert len(version["lines"]) == 4

    for line in version["lines"]:
        assert "unit_cost" not in line
        assert "line_margin" not in line
        # Prices and discounts they agreed to are legitimately visible.
        assert parse(line["unit_list_price"]) > Decimal("0")
        assert "discount_pct" in line


async def test_openapi_portal_schemas_declare_no_cost_or_margin(client) -> None:
    """Structural guarantee: the contract itself has no cost/margin fields."""
    schema = (await client.get("/openapi.json")).json()
    for name in (
        "QuotePublicRead",
        "QuoteVersionPublicRead",
        "QuoteLinePublicRead",
        "OrderPublicRead",
        "QuotePublicSummary",
    ):
        properties = schema["components"]["schemas"][name].get("properties", {})
        leaked = set(properties) & set(FORBIDDEN_KEYS)
        assert not leaked, f"{name} exposes {leaked}"


# ---------------------------------------------------------- conversation
async def test_customer_can_comment_and_ask_line_level_questions(
    seeded, customer
) -> None:
    built = await build_canonical_quote(seeded)
    await _send_to_customer(seeded, built["version_id"])
    detail = (
        await customer.get(f"/portal/quotes/{built['quote']['id']}", expect=200)
    ).json()
    line = detail["current_version"]["lines"][0]

    comment = (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/messages",
            json={"message_type": "COMMENT", "body": "Can we split the delivery?"},
            expect=201,
        )
    ).json()
    assert comment["new_version_id"] is None
    assert comment["requires_reapproval"] is False
    assert comment["message"]["author_kind"] == "CUSTOMER"

    question = (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/messages",
            json={
                "message_type": "QUESTION",
                "body": "Does this laptop include a warranty?",
                "quote_line_id": line["id"],
            },
            expect=201,
        )
    ).json()
    assert question["message"]["quote_line_id"] == line["id"]

    thread = (
        await customer.get(
            f"/portal/quotes/{built['quote']['id']}/messages", expect=200
        )
    ).json()
    assert thread["message_count"] == 2
    assert len(thread["messages"]) == 2
    _assert_no_internal_data(thread, context="GET /portal/.../messages")

    # A comment moves the version into NEGOTIATING but never edits it.
    sales = seeded["sales"]
    version = (
        await sales.get(f"/quote-versions/{built['version_id']}", expect=200)
    ).json()
    assert version["status"] == "NEGOTIATING"
    assert parse(version["total_revenue"]) == Decimal("132710.00")


async def test_customer_cannot_post_seller_or_system_messages(
    seeded, customer
) -> None:
    built = await build_canonical_quote(seeded)
    await _send_to_customer(seeded, built["version_id"])
    for message_type in ("SELLER_REPLY", "SYSTEM"):
        response = await customer.post(
            f"/portal/quotes/{built['quote']['id']}/messages",
            json={"message_type": message_type, "body": "impersonation"},
        )
        assert response.status_code == 422, message_type


async def test_seller_can_reply_and_clears_the_alert(seeded, customer) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await _send_to_customer(seeded, built["version_id"])
    await customer.post(
        f"/portal/quotes/{built['quote']['id']}/messages",
        json={"message_type": "QUESTION", "body": "Warranty terms?"},
        expect=201,
    )

    items = (
        await sales.get(
            "/dashboard/attention-items",
            params={"type": "CUSTOMER_RESPONSE_REQUIRED"},
            expect=200,
        )
    ).json()
    assert items, "the seller must be told the customer is waiting"

    await sales.post(
        f"/quotes/{built['quote']['id']}/negotiation/reply",
        json={"body": "Three years, next-business-day replacement."},
        expect=201,
    )

    thread = (
        await customer.get(
            f"/portal/quotes/{built['quote']['id']}/messages", expect=200
        )
    ).json()
    kinds = [m["author_kind"] for m in thread["messages"]]
    assert "SELLER" in kinds


# --------------------------------------------------------- counter-offers
async def test_counter_offer_creates_a_new_version_and_never_edits_the_old(
    seeded, customer
) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await _send_to_customer(seeded, built["version_id"])

    detail = (
        await customer.get(f"/portal/quotes/{built['quote']['id']}", expect=200)
    ).json()
    laptop = next(
        line
        for line in detail["current_version"]["lines"]
        if "Laptop" in line["description"]
    )

    outcome = (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/messages",
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

    assert outcome["new_version_id"] is not None
    assert outcome["new_version_number"] == 2
    assert outcome["requires_reapproval"] is True
    assert "reviewing the updated terms" in outcome["customer_message"]
    _assert_no_internal_data(outcome, context="counter-offer outcome")

    # V1 is untouched and superseded.
    v1 = (
        await sales.get(f"/quote-versions/{built['version_id']}", expect=200)
    ).json()
    assert v1["status"] == "SUPERSEDED"
    assert parse(v1["total_revenue"]) == Decimal("132710.00")
    laptop_v1 = next(
        line for line in v1["lines"] if "Laptop" in line["description"]
    )
    assert parse(laptop_v1["discount_pct"]) == Decimal("18.0000")

    # V2 carries the requested terms, calculated by the backend.
    v2 = (await sales.get(f"/quote-versions/{outcome['new_version_id']}", expect=200)).json()
    laptop_v2 = next(
        line for line in v2["lines"] if "Laptop" in line["description"]
    )
    assert parse(laptop_v2["discount_pct"]) == Decimal("25.0000")
    assert parse(laptop_v2["net_amount"]) == Decimal("90000.00")
    assert parse(v2["net_revenue"]) == Decimal("124310.00")
    assert v2["source"] == "CUSTOMER_COUNTER"
    assert v2["is_stale"] is True


async def test_counter_offer_triggers_the_decision_fabric_and_stale_approval(
    seeded, customer
) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await _send_to_customer(seeded, built["version_id"])
    detail = (
        await customer.get(f"/portal/quotes/{built['quote']['id']}", expect=200)
    ).json()
    laptop = next(
        line
        for line in detail["current_version"]["lines"]
        if "Laptop" in line["description"]
    )
    outcome = (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/messages",
            json={
                "message_type": "COUNTER_OFFER",
                "body": "25% please",
                "lines": [
                    {"quote_line_id": laptop["id"], "requested_discount_pct": "25"}
                ],
            },
            expect=201,
        )
    ).json()

    impact = (
        await sales.get(
            f"/quote-versions/{outcome['new_version_id']}/impact", expect=200
        )
    ).json()
    assert impact["has_material_change"] is True
    assert impact["blocks_confirmation"] is True
    assert len(impact["stale_decisions"]) == 1
    assert impact["stale_decisions"][0]["previous_decision"] == "APPROVED"
    assert impact["required_approvals"]
    assert "The customer's counter-offer" in impact["explanation"]["summary"]


async def test_counter_offer_can_change_quantity(seeded, customer) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await _send_to_customer(seeded, built["version_id"])
    detail = (
        await customer.get(f"/portal/quotes/{built['quote']['id']}", expect=200)
    ).json()
    monitor = next(
        line
        for line in detail["current_version"]["lines"]
        if "Monitor" in line["description"]
    )
    outcome = (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/messages",
            json={
                "message_type": "CHANGE_REQUEST",
                "body": "We only need 60 monitors.",
                "lines": [
                    {"quote_line_id": monitor["id"], "requested_quantity": "60"}
                ],
            },
            expect=201,
        )
    ).json()
    v2 = (
        await sales.get(f"/quote-versions/{outcome['new_version_id']}", expect=200)
    ).json()
    new_monitor = next(
        line for line in v2["lines"] if "Monitor" in line["description"]
    )
    assert parse(new_monitor["quantity"]) == Decimal("60.0000")


async def test_counter_offer_must_reference_a_line_on_the_current_version(
    seeded, customer
) -> None:
    built = await build_canonical_quote(seeded)
    await _send_to_customer(seeded, built["version_id"])
    response = await customer.post(
        f"/portal/quotes/{built['quote']['id']}/messages",
        json={
            "message_type": "COUNTER_OFFER",
            "body": "discount this",
            "lines": [
                {
                    "quote_line_id": "00000000-0000-0000-0000-000000000000",
                    "requested_discount_pct": "30",
                }
            ],
        },
    )
    assert response.status_code == 404


async def test_counter_offer_requires_a_requested_change(seeded, customer) -> None:
    built = await build_canonical_quote(seeded)
    await _send_to_customer(seeded, built["version_id"])
    detail = (
        await customer.get(f"/portal/quotes/{built['quote']['id']}", expect=200)
    ).json()
    line = detail["current_version"]["lines"][0]

    # No lines at all.
    assert (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/messages",
            json={"message_type": "COUNTER_OFFER", "body": "make it cheaper"},
        )
    ).status_code == 422
    # A line with no requested change.
    assert (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/messages",
            json={
                "message_type": "COUNTER_OFFER",
                "body": "make it cheaper",
                "lines": [{"quote_line_id": line["id"]}],
            },
        )
    ).status_code == 422


async def test_customer_cannot_dictate_the_unit_price(seeded, customer) -> None:
    """Only discount and quantity are negotiable; list price is the seller's."""
    built = await build_canonical_quote(seeded)
    await _send_to_customer(seeded, built["version_id"])
    detail = (
        await customer.get(f"/portal/quotes/{built['quote']['id']}", expect=200)
    ).json()
    line = detail["current_version"]["lines"][0]
    response = await customer.post(
        f"/portal/quotes/{built['quote']['id']}/messages",
        json={
            "message_type": "COUNTER_OFFER",
            "body": "we will pay 100 each",
            "lines": [
                {"quote_line_id": line["id"], "requested_unit_price": "100"}
            ],
        },
    )
    assert response.status_code == 422  # extra="forbid" rejects the field


async def test_confirmation_is_blocked_until_reapproval(seeded, customer) -> None:
    built = await build_canonical_quote(seeded)
    manager, finance = seeded["manager"], seeded["finance"]
    await _send_to_customer(seeded, built["version_id"])

    detail = (
        await customer.get(f"/portal/quotes/{built['quote']['id']}", expect=200)
    ).json()
    assert detail["can_confirm"] is True

    laptop = next(
        line
        for line in detail["current_version"]["lines"]
        if "Laptop" in line["description"]
    )
    await customer.post(
        f"/portal/quotes/{built['quote']['id']}/messages",
        json={
            "message_type": "COUNTER_OFFER",
            "body": "25%",
            "lines": [{"quote_line_id": laptop["id"], "requested_discount_pct": "25"}],
        },
        expect=201,
    )

    # Blocked, with a customer-safe reason that reveals nothing internal.
    blocked = (
        await customer.get(f"/portal/quotes/{built['quote']['id']}", expect=200)
    ).json()
    assert blocked["can_confirm"] is False
    assert "being reviewed by our team" in blocked["blocked_reason"]
    _assert_no_internal_data(blocked, context="blocked portal detail")

    response = await customer.post(
        f"/portal/quotes/{built['quote']['id']}/confirm", json={}
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "STALE_APPROVAL"

    # Re-approve, then confirmation opens up.
    v2_id = blocked["current_version"]["id"]
    for approver in (manager, finance):
        inbox = (await approver.get("/approvals/inbox", expect=200)).json()
        item = next(i for i in inbox if str(i["quote_version_id"]) == str(v2_id))
        await approver.post(
            f"/approvals/{item['approval_request_id']}/approve",
            json={"reason": "re-approved"},
            expect=200,
        )

    unblocked = (
        await customer.get(f"/portal/quotes/{built['quote']['id']}", expect=200)
    ).json()
    assert unblocked["can_confirm"] is True
    assert unblocked["blocked_reason"] is None


async def test_confirmation_is_blocked_while_an_approval_is_pending(
    seeded, customer
) -> None:
    built = await build_canonical_quote(seeded)
    await _send_to_customer(seeded, built["version_id"])
    detail = (
        await customer.get(f"/portal/quotes/{built['quote']['id']}", expect=200)
    ).json()
    laptop = next(
        line
        for line in detail["current_version"]["lines"]
        if "Laptop" in line["description"]
    )
    await customer.post(
        f"/portal/quotes/{built['quote']['id']}/messages",
        json={
            "message_type": "COUNTER_OFFER",
            "body": "22%",
            "lines": [{"quote_line_id": laptop["id"], "requested_discount_pct": "22"}],
        },
        expect=201,
    )
    response = await customer.post(
        f"/portal/quotes/{built['quote']['id']}/confirm", json={}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] in ("STALE_APPROVAL", "APPROVAL_REQUIRED")


async def test_negotiating_a_confirmed_quote_is_refused(seeded, customer) -> None:
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "5", "5"),)
    )
    sales = seeded["sales"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    await sales.post(
        f"/quote-versions/{built['version_id']}/send", json={}, expect=200
    )
    await customer.post(
        f"/portal/quotes/{built['quote']['id']}/confirm", json={}, expect=200
    )

    response = await customer.post(
        f"/portal/quotes/{built['quote']['id']}/messages",
        json={"message_type": "COMMENT", "body": "actually..."},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_CONFIRMED"
