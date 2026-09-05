"""CommercialEngine: exact Decimal arithmetic, totals, margin, snapshots."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.enums import BillingType
from app.services.commercial_engine import (
    CommercialEngine,
    money,
    pct,
    safe_pct,
    unit,
)
from tests.conftest import build_canonical_quote, money as parse


# --------------------------------------------------------------- pure maths
def test_line_calculation_without_discount() -> None:
    calc = CommercialEngine.calculate_line(
        quantity=Decimal("100"),
        unit_list_price=Decimal("1200"),
        unit_cost=Decimal("800"),
    )
    assert calc.gross_amount == Decimal("120000.00")
    assert calc.discount_amount == Decimal("0.00")
    assert calc.net_amount == Decimal("120000.00")
    assert calc.line_cost == Decimal("80000.00")
    assert calc.line_margin == Decimal("40000.00")
    # 40000 / 120000 = 33.3333%
    assert calc.line_margin_pct == Decimal("33.3333")


def test_line_calculation_with_discount() -> None:
    calc = CommercialEngine.calculate_line(
        quantity=Decimal("100"),
        unit_list_price=Decimal("1200"),
        unit_cost=Decimal("800"),
        discount_pct=Decimal("18"),
    )
    assert calc.gross_amount == Decimal("120000.00")
    assert calc.discount_amount == Decimal("21600.00")
    assert calc.net_amount == Decimal("98400.00")
    assert calc.unit_net_price == Decimal("984.0000")
    assert calc.line_cost == Decimal("80000.00")
    assert calc.line_margin == Decimal("18400.00")
    assert calc.line_margin_pct == Decimal("18.6992")


def test_line_calculation_applies_tax_to_net_not_gross() -> None:
    calc = CommercialEngine.calculate_line(
        quantity=Decimal("10"),
        unit_list_price=Decimal("100"),
        unit_cost=Decimal("60"),
        discount_pct=Decimal("10"),
        tax_rate_pct=Decimal("8.25"),
    )
    assert calc.net_amount == Decimal("900.00")
    assert calc.tax_amount == Decimal("74.25")  # 900 * 8.25%
    assert calc.total_amount == Decimal("974.25")
    # Margin ignores tax entirely: tax is not the seller's revenue.
    assert calc.line_margin == Decimal("300.00")


def test_recurring_line_multiplies_by_period_count() -> None:
    """A 12-month plan at 50/month is 600 of contract value, not 50."""
    calc = CommercialEngine.calculate_line(
        quantity=Decimal("1"),
        unit_list_price=Decimal("50"),
        unit_cost=Decimal("10"),
        recurring_periods=12,
    )
    assert calc.gross_amount == Decimal("600.00")
    assert calc.line_cost == Decimal("120.00")
    assert calc.line_margin == Decimal("480.00")


def test_fractional_quantity_is_supported() -> None:
    calc = CommercialEngine.calculate_line(
        quantity=Decimal("1.5"),
        unit_list_price=Decimal("500"),
        unit_cost=Decimal("150"),
    )
    assert calc.net_amount == Decimal("750.00")
    assert calc.line_cost == Decimal("225.00")


def test_zero_revenue_line_does_not_divide_by_zero() -> None:
    calc = CommercialEngine.calculate_line(
        quantity=Decimal("1"),
        unit_list_price=Decimal("0"),
        unit_cost=Decimal("0"),
    )
    assert calc.net_amount == Decimal("0.00")
    assert calc.line_margin_pct == Decimal("0.0000")


def test_hundred_percent_discount_is_legal_and_negative_margin() -> None:
    calc = CommercialEngine.calculate_line(
        quantity=Decimal("1"),
        unit_list_price=Decimal("100"),
        unit_cost=Decimal("60"),
        discount_pct=Decimal("100"),
    )
    assert calc.net_amount == Decimal("0.00")
    assert calc.line_margin == Decimal("-60.00")


def test_rounding_is_half_up_not_bankers() -> None:
    """Python's default is ROUND_HALF_EVEN, which finance does not use."""
    assert money(Decimal("0.005")) == Decimal("0.01")
    assert money(Decimal("0.015")) == Decimal("0.02")
    assert money(Decimal("2.675")) == Decimal("2.68")
    assert unit(Decimal("0.00005")) == Decimal("0.0001")
    assert pct(Decimal("1.00005")) == Decimal("1.0001")


def test_safe_pct_handles_zero_denominator() -> None:
    assert safe_pct(Decimal("10"), Decimal("0")) == Decimal("0.0000")
    assert safe_pct(Decimal("1"), Decimal("3")) == Decimal("33.3333")


def test_totals_are_the_sum_of_rounded_lines() -> None:
    """Printed line items must add up to the printed total, to the cent."""
    calcs = [
        (
            CommercialEngine.calculate_line(
                quantity=Decimal("3"),
                unit_list_price=Decimal("33.333"),
                unit_cost=Decimal("10"),
            ),
            BillingType.ONE_TIME,
        )
        for _ in range(7)
    ]
    totals = CommercialEngine.total_from_calculations(calcs)
    assert totals.net_revenue == sum(c.net_amount for c, _ in calcs)
    assert totals.total_cost == sum(c.line_cost for c, _ in calcs)
    assert totals.margin == totals.net_revenue - totals.total_cost


def test_totals_split_one_time_and_recurring_revenue() -> None:
    one_time = CommercialEngine.calculate_line(
        quantity=Decimal("1"), unit_list_price=Decimal("1000"), unit_cost=Decimal("400")
    )
    recurring = CommercialEngine.calculate_line(
        quantity=Decimal("1"),
        unit_list_price=Decimal("300"),
        unit_cost=Decimal("50"),
        recurring_periods=2,
    )
    totals = CommercialEngine.total_from_calculations(
        [(one_time, BillingType.ONE_TIME), (recurring, BillingType.RECURRING)]
    )
    assert totals.one_time_revenue == Decimal("1000.00")
    assert totals.recurring_revenue == Decimal("600.00")
    assert totals.net_revenue == Decimal("1600.00")
    assert totals.total_cost == Decimal("500.00")
    assert totals.margin == Decimal("1100.00")


def test_effective_discount_pct_is_weighted_not_averaged() -> None:
    """A big undiscounted line must dilute a small deeply-discounted one."""
    deep = CommercialEngine.calculate_line(
        quantity=Decimal("1"),
        unit_list_price=Decimal("100"),
        unit_cost=Decimal("10"),
        discount_pct=Decimal("50"),
    )
    none = CommercialEngine.calculate_line(
        quantity=Decimal("1"),
        unit_list_price=Decimal("900"),
        unit_cost=Decimal("100"),
    )
    totals = CommercialEngine.total_from_calculations(
        [(deep, BillingType.ONE_TIME), (none, BillingType.ONE_TIME)]
    )
    # 50 discount on 1000 gross = 5%, not the 25% a naive average would give.
    assert totals.effective_discount_pct == Decimal("5.0000")


# ------------------------------------------------------- through the API
async def test_canonical_quote_totals_match_hand_calculation(seeded) -> None:
    """The demo configuration, computed by hand:

    100 laptops  @1200 -18% -> 98,400  cost 80,000
    100 monitors @ 400 -16% -> 33,600  cost 20,000
    1 installation @500 -18% ->    410  cost    150
    1 annual support @300  0% ->    300  cost     50
                              --------        -------
                     net    132,710   cost  100,200
                     margin  32,510   -> 24.4970%
    """
    built = await build_canonical_quote(seeded)
    version = built["version"]

    assert parse(version["gross_revenue"]) == Decimal("160800.00")
    assert parse(version["total_discount"]) == Decimal("28090.00")
    assert parse(version["net_revenue"]) == Decimal("132710.00")
    assert parse(version["tax_amount"]) == Decimal("0.00")
    assert parse(version["total_revenue"]) == Decimal("132710.00")
    assert parse(version["total_cost"]) == Decimal("100200.00")
    assert parse(version["margin"]) == Decimal("32510.00")
    assert parse(version["margin_pct"]) == Decimal("24.4970")
    assert parse(version["effective_discount_pct"]) == Decimal("17.4689")
    assert parse(version["one_time_revenue"]) == Decimal("132410.00")
    assert parse(version["recurring_revenue"]) == Decimal("300.00")


async def test_line_totals_sum_to_version_totals(seeded) -> None:
    built = await build_canonical_quote(seeded)
    lines = built["version"]["lines"]
    assert len(lines) == 4
    assert sum(parse(line["net_amount"]) for line in lines) == parse(
        built["version"]["net_revenue"]
    )
    assert sum(parse(line["line_cost"]) for line in lines) == parse(
        built["version"]["total_cost"]
    )
    assert sum(parse(line["discount_amount"]) for line in lines) == parse(
        built["version"]["total_discount"]
    )


async def test_money_is_serialised_as_string_to_avoid_float_loss(seeded) -> None:
    built = await build_canonical_quote(seeded)
    raw = built["version"]["net_revenue"]
    assert isinstance(raw, str), "money must cross the wire as a string"
    assert Decimal(raw) == Decimal("132710.00")


async def test_client_cannot_supply_cost(seeded) -> None:
    """Cost is copied from the catalog; a client field would be rejected."""
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    line = built["version"]["lines"][0]
    response = await sales.patch(
        f"/quote-versions/{built['version_id']}/lines/{line['id']}",
        json={"unit_cost": "1"},
    )
    assert response.status_code == 422  # extra="forbid"


async def test_recalculate_is_idempotent(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    first = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/calculate", expect=200
        )
    ).json()
    second = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/calculate", expect=200
        )
    ).json()
    for field in ("net_revenue", "total_cost", "margin", "margin_pct"):
        assert first[field] == second[field] == built["version"][field]


async def test_calculation_persists_a_current_snapshot(seeded) -> None:
    import uuid

    from app.services.commercial_engine import CommercialEngine as Engine
    from tests.conftest import db_session

    built = await build_canonical_quote(seeded)
    async with db_session() as session:
        snapshot = await Engine.current_snapshot(
            session, uuid.UUID(built["version_id"])
        )
    assert snapshot is not None
    assert snapshot.is_current is True
    assert snapshot.revenue == Decimal("132710.00")
    assert snapshot.cost == Decimal("100200.00")
    assert snapshot.margin == Decimal("32510.00")
    assert snapshot.customer_tier.value == "GOLD"
    assert len(snapshot.snapshot_json["lines"]) == 4
    # The snapshot stores money as strings so JSONB never sees a float.
    assert snapshot.snapshot_json["totals"]["net_revenue"] == "132710.00"


async def test_updating_a_line_recalculates_the_version(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    laptop = next(
        line for line in built["version"]["lines"] if "Laptop" in line["description"]
    )
    updated = (
        await sales.patch(
            f"/quote-versions/{built['version_id']}/lines/{laptop['id']}",
            json={"discount_pct": "0"},
            expect=200,
        )
    ).json()
    # Removing the 21,600 laptop discount raises net revenue by exactly that.
    assert parse(updated["net_revenue"]) == Decimal("154310.00")
    assert parse(updated["total_discount"]) == Decimal("6490.00")


async def test_deleting_a_line_recalculates_the_version(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    support = next(
        line for line in built["version"]["lines"] if "Support" in line["description"]
    )
    await sales.delete(
        f"/quote-versions/{built['version_id']}/lines/{support['id']}", expect=204
    )
    version = (
        await sales.get(f"/quote-versions/{built['version_id']}", expect=200)
    ).json()
    assert len(version["lines"]) == 3
    assert parse(version["recurring_revenue"]) == Decimal("0.00")
    assert parse(version["net_revenue"]) == Decimal("132410.00")


@pytest.mark.parametrize(
    ("quantity", "price", "discount", "expected_net"),
    [
        ("1", "0.01", "0", "0.01"),
        ("3", "0.10", "50", "0.15"),
        ("7", "1.005", "0", "7.04"),  # 7.035 -> half-up -> 7.04
        ("1000000", "9999.99", "0", "9999990000.00"),
    ],
)
def test_edge_case_amounts(
    quantity: str, price: str, discount: str, expected_net: str
) -> None:
    calc = CommercialEngine.calculate_line(
        quantity=Decimal(quantity),
        unit_list_price=Decimal(price),
        unit_cost=Decimal("0"),
        discount_pct=Decimal(discount),
    )
    assert calc.net_amount == Decimal(expected_net)
