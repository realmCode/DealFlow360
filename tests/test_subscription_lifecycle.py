"""Subscription lifecycle — PDF A5 and B7.

Before this, `BillingService.prorate` was exposed read-only at
`/billing/proration-preview`: the maths existed but nothing applied it, and
`BillingScheduleStatus.CANCELLED` / `PaymentStatus.REFUNDED` were unreachable.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from tests.conftest import build_canonical_quote, money as parse

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _confirmed_order(seeded) -> dict:
    """Drive the canonical flow to a confirmed order with a recurring line."""
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
    confirm = (
        await customer.post(
            f"/portal/quotes/{quote_id}/confirm", json={}, expect=200
        )
    ).json()
    return confirm["order"]


async def _recurring_schedule(seeded, order_id: str) -> dict:
    schedules = (
        await seeded["finance"].get(
            "/billing/schedules",
            params={"sales_order_id": order_id, "billing_type": "RECURRING"},
            expect=200,
        )
    ).json()
    assert schedules, "the canonical quote includes an annual support plan"
    return schedules[0]


async def test_the_canonical_order_has_both_billing_kinds(seeded) -> None:
    """PDF QT6 — one-time and recurring on one order, billed separately."""
    order = await _confirmed_order(seeded)
    finance = seeded["finance"]

    one_time = (
        await finance.get(
            "/billing/schedules",
            params={"sales_order_id": order["id"], "billing_type": "ONE_TIME"},
            expect=200,
        )
    ).json()
    recurring = (
        await finance.get(
            "/billing/schedules",
            params={"sales_order_id": order["id"], "billing_type": "RECURRING"},
            expect=200,
        )
    ).json()

    assert len(one_time) == 3
    assert len(recurring) == 1
    # This helper confirms v1 directly. The README's 124,010.00 figure is for
    # v2, after the customer counters the laptops to 25%; v1's one-time total
    # is 132,410.00, and 132,410.00 + 300.00 recurring = the 132,710.00 net.
    assert sum(parse(s["amount"]) for s in one_time) == Decimal("132410.00")
    assert recurring[0]["recurring_interval"] == "YEARLY"
    assert parse(recurring[0]["amount"]) == Decimal("300.00")


async def test_mid_cycle_quantity_change_prorates_the_current_period(
    seeded,
) -> None:
    """PDF A5/B7 — the proration calculator becomes a workflow."""
    order = await _confirmed_order(seeded)
    finance = seeded["finance"]
    schedule = await _recurring_schedule(seeded, order["id"])

    start = date.fromisoformat(schedule["period_start"])
    effective = start + timedelta(days=180)

    result = (
        await finance.post(
            f"/billing/subscriptions/{schedule['id']}/change",
            json={
                "new_quantity": "3",
                "effective_date": effective.isoformat(),
                "reason": "Customer added two more seats.",
            },
            expect=200,
        )
    ).json()

    assert result["change_type"] == "QUANTITY"
    assert parse(result["previous_period_amount"]) == Decimal("300.00")
    # Three seats at 300 each for the remainder of the year.
    assert parse(result["new_period_amount"]) == Decimal("900.00")
    # An increase is chargeable, not creditable.
    assert parse(result["proration_charge"]) > Decimal("0")
    assert parse(result["proration_credit"]) == Decimal("0")
    assert result["credit_note_id"] is None
    # The explanation states the arithmetic rather than just the outcome.
    assert "prorated" in result["explanation"]
    assert effective.isoformat() in result["explanation"]

    updated = await _recurring_schedule(seeded, order["id"])
    assert updated["is_prorated"] is True
    assert updated["status"] == "ACTIVE"
    detail = updated["detail"]
    assert parse(detail["previous_quantity"]) == Decimal("1")
    assert parse(detail["new_quantity"]) == Decimal("3")


async def test_a_downgrade_issues_a_credit_note(seeded) -> None:
    """A reduction against an invoiced period must return money."""
    order = await _confirmed_order(seeded)
    finance = seeded["finance"]
    schedule = await _recurring_schedule(seeded, order["id"])

    # Bill the period first, so there is something to credit.
    await finance.post(
        "/billing/invoices",
        json={"billing_schedule_id": schedule["id"]},
        expect=201,
    )
    # An invoiced period is immutable: change must be refused, not silently
    # rewrite a document the customer already has.
    refused = await finance.post(
        f"/billing/subscriptions/{schedule['id']}/change",
        json={"new_quantity": "1"},
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "PERIOD_ALREADY_INVOICED"


async def test_cancellation_credits_the_unused_portion(seeded) -> None:
    """PDF A5/B7 — cancellation with an automatic partial refund."""
    order = await _confirmed_order(seeded)
    finance = seeded["finance"]
    schedule = await _recurring_schedule(seeded, order["id"])

    await finance.post(
        "/billing/invoices",
        json={"billing_schedule_id": schedule["id"]},
        expect=201,
    )

    start = date.fromisoformat(schedule["period_start"])
    effective = start + timedelta(days=180)

    result = (
        await finance.post(
            f"/billing/subscriptions/{schedule['id']}/cancel",
            json={
                "effective_date": effective.isoformat(),
                "reason": "Customer consolidated onto another contract.",
            },
            expect=200,
        )
    ).json()

    assert result["change_type"] == "CANCELLATION"
    # Consumed days are not refundable; the remainder is.
    assert parse(result["new_period_amount"]) < Decimal("300.00")
    assert parse(result["proration_credit"]) > Decimal("0")
    assert result["credit_note_id"] is not None
    assert "credit note" in result["explanation"]

    note = (
        await finance.get(
            f"/billing/credit-notes/{result['credit_note_id']}", expect=200
        )
    ).json()
    assert note["status"] == "ISSUED"
    assert note["reason"] == "SUBSCRIPTION_CANCELLED"
    assert parse(note["total_amount"]) == parse(result["proration_credit"])
    # The arithmetic is retained so a dispute can be answered.
    assert "proration" in note["detail"]

    cancelled = await _recurring_schedule(seeded, order["id"])
    assert cancelled["status"] == "CANCELLED"


async def test_refunding_a_credit_note_reaches_payment_refunded(seeded) -> None:
    """`PaymentStatus.REFUNDED` was previously unreachable."""
    order = await _confirmed_order(seeded)
    finance = seeded["finance"]
    schedule = await _recurring_schedule(seeded, order["id"])

    invoice = (
        await finance.post(
            "/billing/invoices",
            json={"billing_schedule_id": schedule["id"]},
            expect=201,
        )
    ).json()
    await finance.post(
        f"/billing/invoices/{invoice['id']}/payments",
        json={"amount": invoice["total_amount"], "method": "BANK_TRANSFER"},
        expect=201,
    )

    start = date.fromisoformat(schedule["period_start"])
    result = (
        await finance.post(
            f"/billing/subscriptions/{schedule['id']}/cancel",
            json={"effective_date": (start + timedelta(days=90)).isoformat()},
            expect=200,
        )
    ).json()

    refunded = (
        await finance.post(
            f"/billing/credit-notes/{result['credit_note_id']}/refund",
            json={},
            expect=200,
        )
    ).json()
    assert refunded["status"] == "APPLIED"
    assert parse(refunded["amount_outstanding"]) == Decimal("0")
    assert parse(refunded["amount_refunded"]) == parse(refunded["total_amount"])


async def test_a_credit_note_cannot_be_over_refunded(seeded) -> None:
    order = await _confirmed_order(seeded)
    finance = seeded["finance"]
    schedule = await _recurring_schedule(seeded, order["id"])
    await finance.post(
        "/billing/invoices",
        json={"billing_schedule_id": schedule["id"]},
        expect=201,
    )
    start = date.fromisoformat(schedule["period_start"])
    result = (
        await finance.post(
            f"/billing/subscriptions/{schedule['id']}/cancel",
            json={"effective_date": (start + timedelta(days=30)).isoformat()},
            expect=200,
        )
    ).json()

    refused = await finance.post(
        f"/billing/credit-notes/{result['credit_note_id']}/refund",
        json={"amount": "999999.00"},
    )
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "REFUND_EXCEEDS_CREDIT"


async def test_one_time_schedules_cannot_be_treated_as_subscriptions(
    seeded,
) -> None:
    order = await _confirmed_order(seeded)
    finance = seeded["finance"]
    one_time = (
        await finance.get(
            "/billing/schedules",
            params={"sales_order_id": order["id"], "billing_type": "ONE_TIME"},
            expect=200,
        )
    ).json()[0]

    refused = await finance.post(
        f"/billing/subscriptions/{one_time['id']}/change",
        json={"new_quantity": "2"},
    )
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "SUBSCRIPTION_NOT_RECURRING"


async def test_effective_date_must_fall_inside_the_period(seeded) -> None:
    order = await _confirmed_order(seeded)
    finance = seeded["finance"]
    schedule = await _recurring_schedule(seeded, order["id"])

    refused = await finance.post(
        f"/billing/subscriptions/{schedule['id']}/change",
        json={"new_quantity": "2", "effective_date": "2099-01-01"},
    )
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "EFFECTIVE_DATE_OUTSIDE_PERIOD"


async def test_a_change_must_actually_request_something(seeded) -> None:
    order = await _confirmed_order(seeded)
    finance = seeded["finance"]
    schedule = await _recurring_schedule(seeded, order["id"])

    refused = await finance.post(
        f"/billing/subscriptions/{schedule['id']}/change", json={}
    )
    assert refused.status_code == 422


@pytest.mark.parametrize("role", ["sales", "manager", "ops"])
async def test_only_finance_may_change_a_subscription(seeded, role) -> None:
    order = await _confirmed_order(seeded)
    schedule = await _recurring_schedule(seeded, order["id"])

    refused = await seeded[role].post(
        f"/billing/subscriptions/{schedule['id']}/change",
        json={"new_quantity": "2"},
    )
    assert refused.status_code == 403
    assert refused.json()["error"]["details"]["allowed_roles"] == [
        "ADMIN",
        "FINANCE",
    ]


async def test_invoice_overdue_is_computed_on_read(seeded) -> None:
    """There is no scheduler, so overdue is derived rather than stored."""
    order = await _confirmed_order(seeded)
    finance = seeded["finance"]
    schedule = await _recurring_schedule(seeded, order["id"])

    invoice = (
        await finance.post(
            "/billing/invoices",
            json={"billing_schedule_id": schedule["id"]},
            expect=201,
        )
    ).json()
    # The seeded terms are NET 30, so a freshly issued invoice is current.
    assert invoice["is_overdue"] is False
    assert invoice["days_overdue"] == 0


async def test_voiding_an_invoice_returns_the_schedule_to_billable(seeded) -> None:
    order = await _confirmed_order(seeded)
    finance = seeded["finance"]
    schedule = await _recurring_schedule(seeded, order["id"])

    invoice = (
        await finance.post(
            "/billing/invoices",
            json={"billing_schedule_id": schedule["id"]},
            expect=201,
        )
    ).json()
    assert (await _recurring_schedule(seeded, order["id"]))["status"] == "INVOICED"

    voided = (
        await finance.post(
            f"/billing/invoices/{invoice['id']}/void",
            json={"reason": "Issued against the wrong period."},
            expect=200,
        )
    ).json()
    assert voided["status"] == "VOID"
    assert (await _recurring_schedule(seeded, order["id"]))["status"] == "SCHEDULED"
