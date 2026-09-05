"""Billing: one-time and recurring schedules, intervals, proration."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.enums import RecurringInterval
from app.services.billing_service import BillingService, add_months
from tests.conftest import build_canonical_quote, money as parse


async def _confirmed_order(seeded, lines) -> dict:
    sales, manager, finance = seeded["sales"], seeded["manager"], seeded["finance"]
    customer = seeded["customer"]
    built = await build_canonical_quote(seeded, lines=lines)
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    for approver in (manager, finance):
        inbox = (await approver.get("/approvals/inbox", expect=200)).json()
        for item in inbox:
            if str(item["quote_version_id"]) == str(built["version_id"]):
                await approver.post(
                    f"/approvals/{item['approval_request_id']}/approve",
                    json={"reason": "ok"},
                    expect=200,
                )
    version = (
        await sales.get(f"/quote-versions/{built['version_id']}", expect=200)
    ).json()
    if version["status"] == "APPROVED":
        await sales.post(
            f"/quote-versions/{built['version_id']}/send", json={}, expect=200
        )
    confirm = (
        await customer.post(
            f"/portal/quotes/{built['quote']['id']}/confirm", json={}, expect=200
        )
    ).json()
    return {"built": built, "order_id": confirm["order"]["id"]}


# ------------------------------------------------------------- pure maths
def test_split_amount_sums_back_exactly() -> None:
    """The classic 100/3 problem: printed periods must add to the total."""
    amounts = BillingService.split_amount(Decimal("100.00"), 3)
    assert amounts == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
    assert sum(amounts) == Decimal("100.00")


@pytest.mark.parametrize(
    ("total", "periods"),
    [("100.00", 3), ("1000.00", 7), ("0.05", 4), ("999.99", 12), ("300.00", 1)],
)
def test_split_amount_is_exact_for_any_shape(total: str, periods: int) -> None:
    amounts = BillingService.split_amount(Decimal(total), periods)
    assert len(amounts) == periods
    assert sum(amounts) == Decimal(total)


def test_split_amount_rejects_zero_periods() -> None:
    with pytest.raises(Exception):
        BillingService.split_amount(Decimal("10"), 0)


def test_add_months_clamps_to_month_end() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)  # leap year
    assert add_months(date(2026, 1, 15), 12) == date(2027, 1, 15)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)


def test_proration_is_day_counted_and_explained() -> None:
    result = BillingService.prorate(
        full_period_amount=Decimal("310.00"),
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        billed_from=date(2026, 1, 16),
    )
    assert result.days_in_period == 31
    assert result.days_billed == 16  # 16th to 31st inclusive
    assert result.proration_factor == Decimal("0.51612903")
    assert result.prorated_amount == Decimal("160.00")
    assert "16 of 31 days" in result.explanation


def test_proration_of_a_full_period_is_a_no_op() -> None:
    result = BillingService.prorate(
        full_period_amount=Decimal("120.00"),
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        billed_from=date(2026, 3, 1),
    )
    assert result.proration_factor == Decimal("1.00000000")
    assert result.prorated_amount == Decimal("120.00")


def test_proration_rejects_a_date_outside_the_period() -> None:
    with pytest.raises(Exception):
        BillingService.prorate(
            full_period_amount=Decimal("100"),
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            billed_from=date(2026, 2, 5),
        )


# --------------------------------------------------------- one-time only
async def test_one_time_lines_produce_one_schedule_each(seeded) -> None:
    result = await _confirmed_order(
        seeded,
        lines=(("HW-LAPTOP-01", "10", "5"), ("SV-INSTALL-01", "1", "5")),
    )
    finance = seeded["finance"]
    schedules = (
        await finance.get(
            "/billing/schedules",
            params={"sales_order_id": result["order_id"]},
            expect=200,
        )
    ).json()

    assert len(schedules) == 2
    for schedule in schedules:
        assert schedule["billing_type"] == "ONE_TIME"
        assert schedule["recurring_interval"] is None
        assert schedule["period_number"] == 1
        assert schedule["total_periods"] == 1
        assert schedule["is_prorated"] is False
        assert schedule["status"] == "SCHEDULED"
        # NET 30 from the confirmation date.
        assert (
            date.fromisoformat(schedule["due_date"])
            - date.fromisoformat(schedule["period_start"])
        ) == timedelta(days=30)

    total = sum(parse(s["amount"]) for s in schedules)
    assert total == Decimal("11875.00")  # 10*1200*0.95 + 500*0.95


# ------------------------------------------------------------- mixed order
async def test_a_single_order_carries_one_time_and_recurring_together(
    seeded,
) -> None:
    """The canonical demo: hardware + install bill once, support recurs."""
    result = await _confirmed_order(
        seeded,
        lines=(
            ("HW-LAPTOP-01", "100", "18"),
            ("HW-MONITOR-27", "100", "16"),
            ("SV-INSTALL-01", "1", "18"),
            ("SB-SUPPORT-01", "1", "0"),
        ),
    )
    finance = seeded["finance"]
    schedules = (
        await finance.get(
            "/billing/schedules",
            params={"sales_order_id": result["order_id"]},
            expect=200,
        )
    ).json()

    one_time = [s for s in schedules if s["billing_type"] == "ONE_TIME"]
    recurring = [s for s in schedules if s["billing_type"] == "RECURRING"]
    assert len(one_time) == 3
    assert len(recurring) == 1

    assert sum(parse(s["amount"]) for s in one_time) == Decimal("132410.00")
    assert recurring[0]["recurring_interval"] == "YEARLY"
    assert parse(recurring[0]["amount"]) == Decimal("300.00")

    summary = (
        await finance.get(
            f"/billing/orders/{result['order_id']}/summary", expect=200
        )
    ).json()
    assert parse(summary["one_time_total"]) == Decimal("132410.00")
    assert parse(summary["recurring_contract_total"]) == Decimal("300.00")
    assert parse(summary["recurring_total_per_year"]) == Decimal("300.00")
    assert parse(summary["grand_total"]) == Decimal("132710.00")
    assert summary["schedule_count"] == 4


async def test_schedules_derive_from_order_lines_not_the_quote(seeded) -> None:
    result = await _confirmed_order(
        seeded, lines=(("HW-LAPTOP-01", "10", "5"), ("SB-SUPPORT-01", "1", "0"))
    )
    sales, finance = seeded["sales"], seeded["finance"]
    order = (await sales.get(f"/orders/{result['order_id']}", expect=200)).json()
    schedules = (
        await finance.get(
            "/billing/schedules",
            params={"sales_order_id": result["order_id"]},
            expect=200,
        )
    ).json()

    line_ids = {line["id"] for line in order["lines"]}
    for schedule in schedules:
        assert schedule["sales_order_line_id"] in line_ids

    # Every line's schedules sum to that line's net amount, exactly.
    for line in order["lines"]:
        mine = [
            s for s in schedules if s["sales_order_line_id"] == line["id"]
        ]
        assert sum(parse(s["amount"]) for s in mine) == parse(line["net_amount"])


async def test_billing_is_created_exactly_once_per_order(seeded) -> None:
    result = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "5", "0"),))
    finance = seeded["finance"]
    first = (
        await finance.get(
            "/billing/schedules",
            params={"sales_order_id": result["order_id"]},
            expect=200,
        )
    ).json()
    # Re-confirming must not duplicate schedules.
    customer = seeded["customer"]
    await customer.post(
        f"/portal/quotes/{result['built']['quote']['id']}/confirm",
        json={},
        expect=200,
    )
    second = (
        await finance.get(
            "/billing/schedules",
            params={"sales_order_id": result["order_id"]},
            expect=200,
        )
    ).json()
    assert len(first) == len(second) == 1


# ------------------------------------------------ intervals and proration
@pytest.mark.parametrize(
    ("interval", "periods", "expected_month_step"),
    [
        (RecurringInterval.MONTHLY, 12, 1),
        (RecurringInterval.QUARTERLY, 4, 3),
        (RecurringInterval.YEARLY, 3, 12),
    ],
)
async def test_recurring_intervals_advance_correctly(
    seeded, interval, periods, expected_month_step
) -> None:
    admin = seeded["admin"]
    product = (
        await admin.post(
            "/admin/products",
            json={
                "sku": f"SB-{interval.value}",
                "name": f"{interval.value.title()} Plan",
                "category": "SUBSCRIPTION",
                "list_price": "120.0000",
                "internal_cost": "20.0000",
                "billing_type": "RECURRING",
                "recurring_interval": interval.value,
                "default_recurring_periods": periods,
            },
            expect=201,
        )
    ).json()

    sales, customer = seeded["sales"], seeded["customer"]
    deal = (
        await sales.post(
            "/deals",
            json={
                "name": f"{interval.value} deal",
                "customer_profile_id": seeded["customer_profile_id"],
            },
            expect=201,
        )
    ).json()
    quote = (
        await sales.post(
            f"/deals/{deal['id']}/quotes",
            json={
                "title": f"{interval.value} plan",
                "lines": [
                    {"product_id": product["id"], "quantity": "1", "discount_pct": "0"}
                ],
            },
            expect=201,
        )
    ).json()
    version_id = quote["current_version_id"]
    await sales.post(f"/quote-versions/{version_id}/submit", json={}, expect=200)
    await sales.post(f"/quote-versions/{version_id}/send", json={}, expect=200)
    confirm = (
        await customer.post(
            f"/portal/quotes/{quote['id']}/confirm", json={}, expect=200
        )
    ).json()

    finance = seeded["finance"]
    schedules = (
        await finance.get(
            "/billing/schedules",
            params={
                "sales_order_id": confirm["order"]["id"],
                "billing_type": "RECURRING",
            },
            expect=200,
        )
    ).json()

    assert len(schedules) == periods
    assert [s["period_number"] for s in schedules] == list(range(1, periods + 1))
    assert all(s["total_periods"] == periods for s in schedules)
    assert all(s["recurring_interval"] == interval.value for s in schedules)

    # Contract value = 120 per period x periods, split exactly.
    assert sum(parse(s["amount"]) for s in schedules) == Decimal("120.00") * periods

    # Periods are contiguous and advance by the right number of months.
    for previous, current in zip(schedules, schedules[1:]):
        previous_end = date.fromisoformat(previous["period_end"])
        current_start = date.fromisoformat(current["period_start"])
        assert current_start == previous_end + timedelta(days=1)
        assert add_months(
            date.fromisoformat(previous["period_start"]), expected_month_step
        ) == current_start


def test_month_aligned_schedule_prorates_the_first_period() -> None:
    """The reusable proration service, applied to a real schedule shape."""
    period_start = date(2026, 1, 16)
    boundary_start = date(2026, 1, 1)
    boundary_end = add_months(boundary_start, 1) - timedelta(days=1)
    result = BillingService.prorate(
        full_period_amount=Decimal("100.00"),
        period_start=boundary_start,
        period_end=boundary_end,
        billed_from=period_start,
    )
    assert result.days_in_period == 31
    assert result.days_billed == 16
    assert result.prorated_amount == Decimal("51.61")


async def test_proration_preview_endpoint(seeded) -> None:
    finance = seeded["finance"]
    body = (
        await finance.get(
            "/billing/proration-preview",
            params={
                "full_period_amount": "310.00",
                "period_start": "2026-01-01",
                "period_end": "2026-01-31",
                "billed_from": "2026-01-16",
            },
            expect=200,
        )
    ).json()
    assert parse(body["prorated_amount"]) == Decimal("160.00")
    assert body["days_billed"] == 16
    assert body["explanation"]


# ------------------------------------------------------------------ P1
async def test_invoice_and_payment_flow(seeded) -> None:
    result = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "10", "5"),))
    finance = seeded["finance"]
    schedules = (
        await finance.get(
            "/billing/schedules",
            params={"sales_order_id": result["order_id"]},
            expect=200,
        )
    ).json()
    schedule = schedules[0]

    invoice = (
        await finance.post(
            "/billing/invoices",
            json={"billing_schedule_id": schedule["id"]},
            expect=201,
        )
    ).json()
    assert invoice["status"] == "ISSUED"
    assert parse(invoice["total_amount"]) == parse(schedule["total_amount"])
    assert parse(invoice["amount_due"]) == parse(schedule["total_amount"])

    # A schedule cannot be invoiced twice.
    duplicate = await finance.post(
        "/billing/invoices", json={"billing_schedule_id": schedule["id"]}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "SCHEDULE_ALREADY_INVOICED"

    half = parse(invoice["total_amount"]) / 2
    partial = (
        await finance.post(
            f"/billing/invoices/{invoice['id']}/payments",
            json={"amount": str(half.quantize(Decimal('0.01'))), "method": "ACH"},
            expect=201,
        )
    ).json()
    assert parse(partial["amount"]) > Decimal("0")

    invoices = (await finance.get("/billing/invoices", expect=200)).json()
    assert invoices[0]["status"] == "PARTIALLY_PAID"

    remaining = parse(invoices[0]["amount_due"])
    await finance.post(
        f"/billing/invoices/{invoice['id']}/payments",
        json={"amount": str(remaining)},
        expect=201,
    )
    invoices = (await finance.get("/billing/invoices", expect=200)).json()
    assert invoices[0]["status"] == "PAID"
    assert parse(invoices[0]["amount_due"]) == Decimal("0.00")


async def test_overpayment_is_refused(seeded) -> None:
    result = await _confirmed_order(seeded, lines=(("HW-LAPTOP-01", "1", "0"),))
    finance = seeded["finance"]
    schedules = (
        await finance.get(
            "/billing/schedules",
            params={"sales_order_id": result["order_id"]},
            expect=200,
        )
    ).json()
    invoice = (
        await finance.post(
            "/billing/invoices",
            json={"billing_schedule_id": schedules[0]["id"]},
            expect=201,
        )
    ).json()
    response = await finance.post(
        f"/billing/invoices/{invoice['id']}/payments",
        json={"amount": "999999.00"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OVERPAYMENT"


async def test_billing_cannot_exist_without_an_order(seeded) -> None:
    """There is no endpoint that creates a schedule from thin air."""
    finance = seeded["finance"]
    schedules = (await finance.get("/billing/schedules", expect=200)).json()
    assert schedules == []
    # And invoices require a real schedule id.
    response = await finance.post(
        "/billing/invoices",
        json={"billing_schedule_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404
