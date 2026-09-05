"""GET /quotes — the workspace Quotations list and Kanban pipeline (PDF B1/B2)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.conftest import build_canonical_quote, login, money as parse, signup

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_list_carries_everything_a_card_needs(seeded) -> None:
    """PDF B2: cards show "customer, amount, and stage" in one request."""
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]

    page = (await sales.get("/quotes", expect=200)).page()
    assert page["total"] == 1
    row = page["items"][0]

    assert row["quote_id"] == built["quote"]["id"]
    assert row["quote_number"] == built["quote"]["quote_number"]
    assert row["customer_display_name"] == "Acme Corporation"
    assert row["customer_tier"] == "GOLD"
    assert row["deal_stage"] == "PROPOSAL"
    assert row["status"] == "OPEN"
    assert row["current_version_status"] == "DRAFT"
    assert parse(row["total_revenue"]) == Decimal("132710.00")
    assert parse(row["margin_pct"]) == Decimal("24.4970")
    assert row["owner_name"] == "Sam Rivera"
    assert row["line_count"] == 4
    assert row["version_count"] == 1
    assert row["age_days"] == 0
    assert row["risk_band"] in ("MEDIUM", "HIGH", "LOW", "NONE", "CRITICAL")


async def test_version_status_filter_separates_the_pipeline_columns(seeded) -> None:
    sales = seeded["sales"]
    built = await build_canonical_quote(seeded)

    draft = (
        await sales.get("/quotes", params={"version_status": "DRAFT"}, expect=200)
    ).page()
    assert draft["total"] == 1

    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )

    pending = (
        await sales.get(
            "/quotes", params={"version_status": "PENDING_APPROVAL"}, expect=200
        )
    ).page()
    assert pending["total"] == 1
    assert pending["items"][0]["requires_approval"] is True

    still_draft = (
        await sales.get("/quotes", params={"version_status": "DRAFT"}, expect=200)
    ).page()
    assert still_draft["total"] == 0


async def test_stale_filter_surfaces_blocked_quotes(seeded) -> None:
    """The stale flag is the single most useful pipeline filter for a manager."""
    sales, manager, finance, customer = (
        seeded["sales"],
        seeded["manager"],
        seeded["finance"],
        seeded["customer"],
    )
    built = await build_canonical_quote(seeded)
    version_id = built["version_id"]
    quote_id = built["quote"]["id"]

    await sales.post(f"/quote-versions/{version_id}/submit", json={}, expect=200)
    inbox = (await manager.get("/approvals/inbox", expect=200)).json()
    request_id = inbox[0]["approval_request_id"]
    await manager.post(
        f"/approvals/{request_id}/approve", json={"reason": "ok"}, expect=200
    )
    await finance.post(
        f"/approvals/{request_id}/approve", json={"reason": "ok"}, expect=200
    )
    await sales.post(f"/quote-versions/{version_id}/send", json={}, expect=200)

    portal = (await customer.get(f"/portal/quotes/{quote_id}", expect=200)).json()
    laptop = next(
        line
        for line in portal["current_version"]["lines"]
        if "Laptop" in line["description"]
    )
    await customer.post(
        f"/portal/quotes/{quote_id}/messages",
        json={
            "message_type": "COUNTER_OFFER",
            "body": "We need 25%.",
            "lines": [{"quote_line_id": laptop["id"], "requested_discount_pct": "25"}],
        },
        expect=201,
    )

    stale = (await sales.get("/quotes", params={"is_stale": True}, expect=200)).page()
    assert stale["total"] == 1
    assert stale["items"][0]["is_stale"] is True
    assert stale["items"][0]["version_count"] == 2


async def test_search_matches_number_title_and_customer(seeded) -> None:
    sales = seeded["sales"]
    built = await build_canonical_quote(seeded, title="Acme laptop refresh")
    number = built["quote"]["quote_number"]

    for needle in (number, "laptop", "Acme"):
        page = (await sales.get("/quotes", params={"q": needle}, expect=200)).page()
        assert page["total"] == 1, needle

    empty = (
        await sales.get("/quotes", params={"q": "zzz-no-match"}, expect=200)
    ).page()
    assert empty["total"] == 0


async def test_quote_list_is_tenant_scoped(client, seeded) -> None:
    await build_canonical_quote(seeded)

    rival = await signup(
        client, email="rival-sales@other.example", organization_name="Rival Corp"
    )
    intruder = await login(client, "rival-sales@other.example")

    page = (await intruder.get("/quotes", expect=200)).page()
    assert page["total"] == 0, "another organization's quotes must not be visible"


async def test_customer_cannot_use_the_internal_quote_list(seeded) -> None:
    refused = await seeded["customer"].get("/quotes")
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "PORTAL_USER_FORBIDDEN"


async def test_losing_a_quote_closes_the_deal_and_leaves_the_pipeline(
    seeded,
) -> None:
    """`QuoteStatus.LOST` and `DealStage.CLOSED_LOST` were both unreachable."""
    sales = seeded["sales"]
    built = await build_canonical_quote(seeded)
    quote_id = built["quote"]["id"]
    deal_id = built["deal"]["id"]

    lost = (
        await sales.post(
            f"/quotes/{quote_id}/lose",
            json={"reason": "Customer chose a competitor on price."},
            expect=200,
        )
    ).json()
    assert lost["status"] == "LOST"

    deal = (await sales.get(f"/deals/{deal_id}", expect=200)).json()
    assert deal["stage"] == "CLOSED_LOST"

    # A second attempt is a conflict, not a silent success.
    again = await sales.post(
        f"/quotes/{quote_id}/lose", json={"reason": "again"}
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "QUOTE_ALREADY_LOST"
