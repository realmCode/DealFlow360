"""Order-level discount (PDF B3) and the governance loophole it could open.

The load-bearing test here is
`test_order_discount_cannot_be_used_to_bypass_a_line_ceiling`. If the order
tier were excluded from ceiling evaluation, a rep could keep every line
nominally compliant and move the real giveaway into an unchecked field —
exactly the evasion PDF section 10 describes.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.conftest import build_canonical_quote, money as parse

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_zero_order_discount_is_a_no_op(seeded) -> None:
    """Regression guard: the canonical numbers must not move."""
    built = await build_canonical_quote(seeded)
    version = built["version"]

    assert parse(version["order_discount_pct"]) == Decimal("0.0000")
    assert parse(version["order_discount_amount"]) == Decimal("0.00")
    # The documented canonical figures, unchanged by the new column.
    assert parse(version["gross_revenue"]) == Decimal("160800.00")
    assert parse(version["total_discount"]) == Decimal("28090.00")
    assert parse(version["net_revenue"]) == Decimal("132710.00")
    assert parse(version["total_cost"]) == Decimal("100200.00")
    assert parse(version["margin"]) == Decimal("32510.00")
    assert parse(version["margin_pct"]) == Decimal("24.4970")


async def test_order_discount_compounds_with_the_line_discount(seeded) -> None:
    sales = seeded["sales"]
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "10"),)
    )
    version_id = built["version_id"]

    updated = (
        await sales.patch(
            f"/quote-versions/{version_id}/discount",
            json={"order_discount_pct": "5"},
            expect=200,
        )
    ).json()

    # gross 10 x 1200 = 12,000; line 10% -> 10,800; order 5% -> 10,260
    assert parse(updated["gross_revenue"]) == Decimal("12000.00")
    assert parse(updated["order_discount_amount"]) == Decimal("540.00")
    assert parse(updated["net_revenue"]) == Decimal("10260.00")
    # Total discount is both tiers: 1,200 + 540.
    assert parse(updated["total_discount"]) == Decimal("1740.00")
    # Compounded, not added: 1 - 0.9 x 0.95 = 14.5%, not 15%.
    assert parse(updated["effective_discount_pct"]) == Decimal("14.5000")

    line = updated["lines"][0]
    assert parse(line["discount_amount"]) == Decimal("1200.00")
    assert parse(line["order_discount_amount"]) == Decimal("540.00")
    assert parse(line["effective_discount_pct"]) == Decimal("14.5000")
    assert parse(line["net_amount"]) == Decimal("10260.00")


async def test_line_amounts_still_sum_to_the_order_total(seeded) -> None:
    """A printed line item must reconcile against the printed total."""
    sales = seeded["sales"]
    built = await build_canonical_quote(seeded)
    version_id = built["version_id"]

    updated = (
        await sales.patch(
            f"/quote-versions/{version_id}/discount",
            json={"order_discount_pct": "7.5"},
            expect=200,
        )
    ).json()

    line_sum = sum(parse(line["net_amount"]) for line in updated["lines"])
    assert line_sum == parse(updated["net_revenue"])

    discount_sum = sum(
        parse(line["discount_amount"]) + parse(line["order_discount_amount"])
        for line in updated["lines"]
    )
    assert discount_sum == parse(updated["total_discount"])


async def test_order_discount_cannot_be_used_to_bypass_a_line_ceiling(
    seeded,
) -> None:
    """The loophole PDF section 10 warns about must stay closed.

    A hardware line at 12% is inside the seeded Gold ceiling of 15%. Adding a
    10% order-level discount pushes the *effective* discount to 20.8%, which
    is a real breach and must be evaluated as one.
    """
    sales = seeded["sales"]
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "12"),)
    )
    version_id = built["version_id"]

    clean = (
        await sales.get(f"/quote-versions/{version_id}/policy-results", expect=200)
    ).json()
    assert clean["requires_approval"] is False, "12% is inside the 15% ceiling"

    await sales.patch(
        f"/quote-versions/{version_id}/discount",
        json={"order_discount_pct": "10"},
        expect=200,
    )
    breached = (
        await sales.get(f"/quote-versions/{version_id}/policy-results", expect=200)
    ).json()

    assert breached["requires_approval"] is True, (
        "an order-level discount that pushes a line past its ceiling must "
        "still require approval"
    )
    violation = next(
        r
        for r in breached["policy_results"]
        if r["status"] == "VIOLATED" and r["rule"] == "CATEGORY_DISCOUNT_CEILING"
    )
    # 1 - 0.88 x 0.90 = 20.8%
    assert parse(violation["actual_value"]) == Decimal("20.8000")
    assert parse(violation["threshold_value"]) == Decimal("15.0000")
    # The result explains both tiers so the approver can see where it came from.
    assert violation["detail"]["line_discount_pct"] == "12.0000"
    assert violation["detail"]["order_discount_pct"] == "10.0000"
    assert violation["detail"]["effective_discount_pct"] == "20.8000"


async def test_order_discount_is_only_editable_on_a_draft(seeded) -> None:
    sales = seeded["sales"]
    built = await build_canonical_quote(seeded)
    version_id = built["version_id"]

    await sales.post(f"/quote-versions/{version_id}/submit", json={}, expect=200)
    refused = await sales.patch(
        f"/quote-versions/{version_id}/discount",
        json={"order_discount_pct": "5"},
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "IMMUTABLE_VERSION"


async def test_order_discount_is_carried_into_a_revision(seeded) -> None:
    """A revision must not silently drop an order-level concession."""
    sales = seeded["sales"]
    built = await build_canonical_quote(seeded)
    version_id = built["version_id"]

    await sales.patch(
        f"/quote-versions/{version_id}/discount",
        json={"order_discount_pct": "4"},
        expect=200,
    )
    await sales.post(f"/quote-versions/{version_id}/submit", json={}, expect=200)

    revision = (
        await sales.post(
            f"/quote-versions/{version_id}/revisions",
            json={"reason": "Customer asked for a longer term."},
            expect=201,
        )
    ).json()
    assert parse(revision["order_discount_pct"]) == Decimal("4.0000")


async def test_order_discount_is_rejected_outside_zero_to_one_hundred(
    seeded,
) -> None:
    sales = seeded["sales"]
    built = await build_canonical_quote(seeded)
    version_id = built["version_id"]

    for value in ("-1", "101"):
        refused = await sales.patch(
            f"/quote-versions/{version_id}/discount",
            json={"order_discount_pct": value},
        )
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "VALIDATION_ERROR"
