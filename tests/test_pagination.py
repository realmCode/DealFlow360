"""The shared list contract: Page envelope, bounds, sorting and period filters."""

from __future__ import annotations

import pytest

from tests.conftest import build_canonical_quote

pytestmark = pytest.mark.asyncio(loop_scope="session")

PAGINATED = (
    "/quotes",
    "/deals",
    "/products",
    "/orders",
    "/audit/events",
    "/dashboard/attention-items",
)


async def test_every_list_endpoint_returns_a_page_envelope(seeded) -> None:
    sales = seeded["sales"]
    for path in PAGINATED:
        page = (await sales.get(path, expect=200)).page()
        assert set(page) >= {"items", "total", "limit", "offset"}, path
        assert isinstance(page["items"], list), path
        assert page["limit"] == 25, path
        assert page["offset"] == 0, path


async def test_limit_and_offset_walk_the_collection(seeded) -> None:
    sales = seeded["sales"]
    # Four seeded products give a stable, small collection to page through.
    first = (await sales.get("/products", params={"limit": 2}, expect=200)).page()
    assert first["total"] == 4
    assert len(first["items"]) == 2

    second = (
        await sales.get("/products", params={"limit": 2, "offset": 2}, expect=200)
    ).page()
    assert second["total"] == 4
    assert len(second["items"]) == 2

    ids = {p["id"] for p in first["items"]} | {p["id"] for p in second["items"]}
    assert len(ids) == 4, "pages must not overlap"

    beyond = (
        await sales.get("/products", params={"limit": 2, "offset": 10}, expect=200)
    ).page()
    assert beyond["items"] == []
    assert beyond["total"] == 4, "total is the unpaginated count"


async def test_limit_bounds_are_enforced(seeded) -> None:
    sales = seeded["sales"]
    for bad in (0, -1, 201, 5000):
        refused = await sales.get("/products", params={"limit": bad})
        assert refused.status_code == 422, bad
        assert refused.json()["error"]["code"] == "VALIDATION_ERROR"

    refused = await sales.get("/products", params={"offset": -1})
    assert refused.status_code == 422


async def test_sort_field_is_allowlisted(seeded) -> None:
    """`sort_by` reaches an ORDER BY, so an arbitrary value must be refused."""
    sales = seeded["sales"]
    refused = await sales.get("/products", params={"sort_by": "internal_cost); DROP"})
    assert refused.status_code == 422
    body = refused.json()["error"]
    assert body["code"] == "INVALID_SORT_FIELD"
    assert "allowed" in body["details"]
    assert "name" in body["details"]["allowed"]


async def test_sort_direction_changes_the_order(seeded) -> None:
    sales = seeded["sales"]
    asc = (
        await sales.get(
            "/products",
            params={"sort_by": "list_price", "sort_dir": "asc"},
            expect=200,
        )
    ).json()
    desc = (
        await sales.get(
            "/products",
            params={"sort_by": "list_price", "sort_dir": "desc"},
            expect=200,
        )
    ).json()
    # Products are grouped by category first, so compare within the group.
    assert [p["sku"] for p in asc] != [p["sku"] for p in desc]


async def test_search_narrows_the_result(seeded) -> None:
    sales = seeded["sales"]
    page = (await sales.get("/products", params={"q": "LAPTOP"}, expect=200)).page()
    assert page["total"] == 1
    assert page["items"][0]["sku"] == "HW-LAPTOP-01"

    empty = (
        await sales.get("/products", params={"q": "nothing-matches"}, expect=200)
    ).page()
    assert empty["total"] == 0
    assert empty["items"] == []


async def test_custom_period_requires_both_bounds(seeded) -> None:
    sales = seeded["sales"]
    refused = await sales.get(
        "/reports/sales-performance", params={"period": "custom"}
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "PERIOD_RANGE_REQUIRED"

    reversed_range = await sales.get(
        "/reports/sales-performance",
        params={
            "period": "custom",
            "date_from": "2026-06-01",
            "date_to": "2026-01-01",
        },
    )
    assert reversed_range.status_code == 422
    assert reversed_range.json()["error"]["code"] == "INVALID_PERIOD_RANGE"


async def test_period_presets_are_accepted(seeded) -> None:
    sales = seeded["sales"]
    for period in ("today", "week", "month", "quarter", "year", "all"):
        report = (
            await sales.get(
                "/reports/sales-performance", params={"period": period}, expect=200
            )
        ).json()
        assert report["filters"]["period"] is not None, period


async def test_deal_stage_filter_supports_the_kanban_board(seeded) -> None:
    sales = seeded["sales"]
    await build_canonical_quote(seeded)

    proposal = (
        await sales.get("/deals", params={"stage": "PROPOSAL"}, expect=200)
    ).page()
    assert proposal["total"] == 1

    qualification = (
        await sales.get("/deals", params={"stage": "QUALIFICATION"}, expect=200)
    ).page()
    assert qualification["total"] == 0
