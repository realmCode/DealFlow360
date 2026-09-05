"""Reporting module — PDF A7.

Arithmetic is checked against the canonical seed quote, whose figures are
hand-computed in the README, so a regression in an aggregate shows up as a
wrong number rather than merely a different one.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.conftest import build_canonical_quote, money as parse

pytestmark = pytest.mark.asyncio(loop_scope="session")

REPORTS = (
    "sales-performance",
    "approval-status",
    "products",
    "discounts",
    "pipeline",
)


async def test_every_report_is_reachable_and_echoes_its_filters(seeded) -> None:
    """An exported report has to be self-describing, so filters come back."""
    sales = seeded["sales"]
    for name in REPORTS:
        report = (await sales.get(f"/reports/{name}", expect=200)).json()
        assert "filters" in report, name
        # The default window is everything, rendered for a human reader.
        assert report["filters"]["period"] == "All time", name
        assert report["filters"]["date_from"] is None, name

    bounded = (
        await sales.get(
            "/reports/sales-performance",
            params={
                "period": "custom",
                "date_from": "2026-01-01",
                "date_to": "2026-12-31",
            },
            expect=200,
        )
    ).json()
    assert bounded["filters"]["period"] == "2026-01-01 to 2026-12-31"
    assert bounded["filters"]["date_from"] == "2026-01-01"


async def test_sales_performance_matches_the_canonical_quote(seeded) -> None:
    sales = seeded["sales"]
    await build_canonical_quote(seeded)

    report = (
        await sales.get(
            "/reports/sales-performance", params={"group_by": "rep"}, expect=200
        )
    ).json()

    assert len(report["rows"]) == 1
    row = report["rows"][0]
    assert row["group_label"] == "Sam Rivera"
    assert row["quote_count"] == 1
    assert parse(row["gross_revenue"]) == Decimal("160800.00")
    assert parse(row["total_discount"]) == Decimal("28090.00")
    assert parse(row["net_revenue"]) == Decimal("132710.00")
    assert parse(row["margin"]) == Decimal("32510.00")
    assert parse(row["margin_pct"]) == Decimal("24.4970")

    totals = report["totals"]
    assert parse(totals["net_revenue"]) == Decimal("132710.00")
    assert parse(totals["effective_discount_pct"]) == Decimal("17.4689")


async def test_group_by_options_are_allowlisted(seeded) -> None:
    sales = seeded["sales"]
    for group_by in ("rep", "customer", "tier", "stage", "status", "month", "risk_band"):
        report = (
            await sales.get(
                "/reports/sales-performance",
                params={"group_by": group_by},
                expect=200,
            )
        ).json()
        assert report["group_by"] == group_by

    refused = await sales.get(
        "/reports/sales-performance", params={"group_by": "nonsense"}
    )
    assert refused.status_code == 422


async def test_rep_filter_narrows_to_one_seller(seeded) -> None:
    sales = seeded["sales"]
    await build_canonical_quote(seeded)
    me = (await sales.get("/users/me", expect=200)).json()

    mine = (
        await sales.get(
            "/reports/sales-performance",
            params={"rep_user_id": me["id"]},
            expect=200,
        )
    ).json()
    assert mine["totals"]["quote_count"] == 1

    other = (
        await sales.get(
            "/reports/sales-performance",
            params={"rep_user_id": seeded["customer_profile_id"]},
            expect=200,
        )
    ).json()
    assert other["totals"]["quote_count"] == 0


async def test_team_filter_uses_the_seeded_team(seeded) -> None:
    """PDF A7.4 — the "Sales Team" half of the filter needs a real entity."""
    sales, admin = seeded["sales"], seeded["admin"]
    await build_canonical_quote(seeded)

    teams = (await admin.get("/admin/sales-teams", expect=200)).json()
    assert teams, "the seed must provide a team for the report filter"
    team = teams[0]
    assert team["code"] == "WEST"
    assert {m["email"] for m in team["members"]} >= {"sales@techsupply.com"}

    report = (
        await sales.get(
            "/reports/sales-performance",
            params={"team_id": team["id"]},
            expect=200,
        )
    ).json()
    assert report["totals"]["quote_count"] == 1


async def test_approval_status_report_reports_every_state(seeded) -> None:
    sales = seeded["sales"]
    built = await build_canonical_quote(seeded)
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )

    report = (await sales.get("/reports/approval-status", expect=200)).json()
    # Zeros are meaningful; an absent key would force the client to guess.
    assert set(report["by_status"]) >= {
        "PENDING",
        "APPROVED",
        "REJECTED",
        "REVISION_REQUESTED",
        "STALE",
        "CANCELLED",
    }
    assert report["by_status"]["PENDING"]["count"] == 1
    assert parse(report["by_status"]["PENDING"]["total_value"]) == Decimal(
        "132710.00"
    )


async def test_product_report_ranks_best_selling_and_most_discounted(
    seeded,
) -> None:
    """Products only appear once they are on a confirmed order."""
    sales = seeded["sales"]
    report = (await sales.get("/reports/products", expect=200)).json()
    assert report["product_count"] == 0, "nothing has been ordered yet"
    assert report["best_selling"] == []
    assert report["most_discounted"] == []


async def test_discount_report_profiles_each_rep(seeded) -> None:
    sales = seeded["sales"]
    built = await build_canonical_quote(seeded)
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )

    report = (await sales.get("/reports/discounts", expect=200)).json()
    assert len(report["by_rep"]) == 1
    rep = report["by_rep"][0]
    assert rep["rep_name"] == "Sam Rivera"
    assert rep["version_count"] == 1
    assert parse(rep["avg_discount_pct"]) == Decimal("17.4689")
    assert rep["required_approval_count"] == 1

    bands = {b["band"]: b["count"] for b in report["distribution"]}
    assert bands["15-20"] == 1, "17.47% falls in the 15-20 band"


async def test_pipeline_report_counts_by_stage(seeded) -> None:
    sales = seeded["sales"]
    await build_canonical_quote(seeded)

    report = (await sales.get("/reports/pipeline", expect=200)).json()
    assert report["total_deals"] == 1
    assert report["by_stage"]["PROPOSAL"]["count"] == 1
    assert report["by_stage"]["CLOSED_WON"]["count"] == 0
    assert report["won_count"] == 0


async def test_reports_are_tenant_scoped(client, seeded) -> None:
    from tests.conftest import login, signup

    await build_canonical_quote(seeded)
    await signup(
        client, email="rival-mgr@other.example", organization_name="Rival Ltd"
    )
    intruder = await login(client, "rival-mgr@other.example")

    report = (await intruder.get("/reports/sales-performance", expect=200)).json()
    assert report["totals"]["quote_count"] == 0
    assert report["rows"] == []


async def test_portal_user_cannot_read_reports(seeded) -> None:
    refused = await seeded["customer"].get("/reports/sales-performance")
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "PORTAL_USER_FORBIDDEN"


# ------------------------------------------------------------------ export
@pytest.mark.parametrize(
    ("fmt", "content_type", "magic"),
    [
        ("csv", "text/csv", b""),
        (
            "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            b"PK",
        ),
        ("pdf", "application/pdf", b"%PDF"),
    ],
)
async def test_export_returns_a_real_binary_file(
    seeded, fmt: str, content_type: str, magic: bytes
) -> None:
    """PDF A7.2 — "Export options: PDF / XLS".

    These are the only non-JSON responses in the API, so the content type and
    the file signature both matter.
    """
    sales = seeded["sales"]
    await build_canonical_quote(seeded)

    response = await sales.get(
        "/reports/sales-performance/export", params={"format": fmt}, expect=200
    )
    assert content_type in response.headers["content-type"]
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert f".{fmt}" in disposition
    assert response.content, "export must not be empty"
    if magic:
        assert response.content.startswith(magic), f"{fmt} signature"


async def test_every_report_exports_in_every_format(seeded) -> None:
    sales = seeded["sales"]
    await build_canonical_quote(seeded)
    for name in REPORTS:
        for fmt in ("csv", "xlsx", "pdf"):
            response = await sales.get(
                f"/reports/{name}/export", params={"format": fmt}, expect=200
            )
            assert response.content, f"{name}.{fmt}"


async def test_export_rejects_an_unknown_format(seeded) -> None:
    sales = seeded["sales"]
    refused = await sales.get(
        "/reports/sales-performance/export", params={"format": "docx"}
    )
    assert refused.status_code == 422


async def test_export_formats_endpoint_advertises_capability(seeded) -> None:
    payload = (await seeded["sales"].get("/reports/export/formats", expect=200)).json()
    assert set(payload["formats"]) == {"csv", "xlsx", "pdf"}
    assert payload["default"] == "xlsx"
    assert set(payload["reports"]) == set(REPORTS)
