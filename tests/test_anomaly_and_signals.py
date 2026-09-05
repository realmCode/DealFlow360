"""B9 signals: discount anomaly, delivery slippage, nudge and escalate.

The anomaly check answers a different question from the PolicyEngine. The
engine asks "is this above the allowed ceiling?"; this asks "is this unusual
*for this person*?" — which can fire on a fully compliant quote and stay
silent on a breaching one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tests.conftest import build_canonical_quote, money as parse, page_items

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _submit(seeded, *, discount: str, sku: str = "HW-LAPTOP-01") -> dict:
    built = await build_canonical_quote(seeded, lines=((sku, "5", discount),))
    await seeded["sales"].post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    return built


# --------------------------------------------------------------- settings
async def test_settings_are_created_from_defaults_on_first_read(seeded) -> None:
    """PDF A3/B9 — thresholds are per-organization, not process-global."""
    admin = seeded["admin"]
    settings = (await admin.get("/admin/settings", expect=200)).json()

    assert parse(settings["finance_escalation_threshold"]) == Decimal("60.0000")
    assert settings["stalled_deal_days"] == 14
    assert parse(settings["discount_anomaly_sigma"]) == Decimal("2.0000")
    assert settings["discount_anomaly_min_samples"] == 5
    assert parse(settings["risk_discount_overage_weight"]) == Decimal("3.0000")


async def test_settings_can_be_tuned_and_affect_routing(seeded) -> None:
    """Lowering the escalation threshold must pull Finance in sooner."""
    admin, sales = seeded["admin"], seeded["sales"]

    built = await build_canonical_quote(seeded)
    baseline = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()
    baseline_levels = {r["type"] for r in baseline["required_approvals"]}

    # The canonical quote scores ~32. Drop the threshold below that and
    # Finance must be added on risk alone.
    await admin.patch(
        "/admin/settings", json={"finance_escalation_threshold": "10"}, expect=200
    )
    tuned = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()
    assert "FINANCE" in {r["type"] for r in tuned["required_approvals"]}
    assert parse(tuned["blended_risk"]["score"]) == parse(
        baseline["blended_risk"]["score"]
    ), "the threshold changes routing, not the score"
    assert baseline_levels is not None


async def test_only_admin_can_read_or_change_settings(seeded) -> None:
    for role in ("sales", "manager", "finance", "ops"):
        refused = await seeded[role].get("/admin/settings")
        assert refused.status_code == 403, role
        assert refused.json()["error"]["details"]["allowed_roles"] == ["ADMIN"]


# -------------------------------------------------------- discount anomaly
async def test_no_anomaly_is_raised_without_enough_history(seeded) -> None:
    """A rep's second quote must not be judged against a single data point."""
    await _submit(seeded, discount="30")

    items = page_items(
        (
            await seeded["sales"].get("/dashboard/attention-items", expect=200)
        ).json()
    )
    assert not [i for i in items if i["type"] == "DISCOUNT_ANOMALY"], (
        "below the minimum sample size the baseline is not trustworthy"
    )


async def test_anomaly_fires_once_a_baseline_exists(seeded) -> None:
    """PDF B9.2 — "a discount well above a rep's historical average"."""
    admin, sales = seeded["admin"], seeded["sales"]
    # Two samples is enough to have a mean and a spread.
    await admin.patch(
        "/admin/settings",
        json={"discount_anomaly_min_samples": 2, "discount_anomaly_sigma": "1.0"},
        expect=200,
    )

    # Establish a consistent, modest discounting pattern.
    for discount in ("4", "5", "4", "6"):
        await _submit(seeded, discount=discount)

    # Then a sharp departure from it — still inside the 15% Gold ceiling.
    built = await _submit(seeded, discount="14")

    items = page_items(
        (await sales.get("/dashboard/attention-items", expect=200)).json()
    )
    anomalies = [i for i in items if i["type"] == "DISCOUNT_ANOMALY"]
    assert anomalies, "a 14% quote from a ~5% seller is a behavioural outlier"

    anomaly = anomalies[0]
    assert anomaly["owner_role"] == "MANAGER"
    # The reason must carry the arithmetic, not just a verdict.
    assert "standard deviations above" in anomaly["reason"]
    assert "average of" in anomaly["reason"]
    assert anomaly["detail"]["baseline"]["sample_count"] >= 2
    assert anomaly["detail"]["is_anomaly"] is True

    # And the quote itself is still policy-compliant, which is the whole point.
    policy = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()
    assert policy["requires_approval"] is False, (
        "14% is inside the Gold hardware ceiling; the anomaly is a separate, "
        "behavioural signal"
    )


async def test_anomaly_report_lists_and_explains(seeded) -> None:
    admin, sales = seeded["admin"], seeded["sales"]
    await admin.patch(
        "/admin/settings",
        json={"discount_anomaly_min_samples": 2, "discount_anomaly_sigma": "1.0"},
        expect=200,
    )
    for discount in ("4", "5", "4"):
        await _submit(seeded, discount=discount)
    await _submit(seeded, discount="14")

    report = (await sales.get("/reports/discount-anomalies", expect=200)).json()
    assert report["anomaly_count"] >= 1
    top = report["items"][0]
    assert top["rep_name"] == "Sam Rivera"
    assert parse(top["deviations_above_mean"]) > Decimal("0")
    assert parse(top["trigger_at_pct"]) > Decimal("0")
    assert top["baseline"]["is_reliable"] is True

    # include_normal exposes the "we checked and it was fine" case.
    with_normal = (
        await sales.get(
            "/reports/discount-anomalies",
            params={"include_normal": True},
            expect=200,
        )
    ).json()
    assert len(with_normal["items"]) > len(report["items"])


# ------------------------------------------------------ delivery slippage
async def test_delivery_promise_and_slippage(seeded) -> None:
    """PDF B9.3 — slippage needs a recorded promise to measure against."""
    from tests.test_subscription_lifecycle import _confirmed_order

    order = await _confirmed_order(seeded)
    sales, ops = seeded["sales"], seeded["ops"]

    # Anchor on the server's clock, not the runner's. Every timestamp in this
    # system is UTC, so a local `date.today()` disagrees by a day whenever the
    # runner sits east of Greenwich past midnight local time.
    today = datetime.now(UTC).date()

    fresh = (
        await sales.patch(
            f"/orders/{order['id']}/promise",
            json={"promised_delivery_date": (today + timedelta(days=7)).isoformat()},
            expect=200,
        )
    ).json()
    assert fresh["is_delivery_late"] is False
    assert fresh["days_late"] == 0

    late = (
        await sales.patch(
            f"/orders/{order['id']}/promise",
            json={"promised_delivery_date": (today - timedelta(days=3)).isoformat()},
            expect=200,
        )
    ).json()
    assert late["is_delivery_late"] is True
    assert late["days_late"] == 3

    overdue = (
        await ops.get("/orders", params={"overdue_delivery": True}, expect=200)
    ).page()
    assert overdue["total"] == 1
    assert overdue["items"][0]["days_late"] == 3


async def test_delivery_confirmation_reaches_delivered(seeded) -> None:
    """`FulfillmentStatus.DELIVERED` was previously unreachable."""
    from tests.test_subscription_lifecycle import _confirmed_order

    order = await _confirmed_order(seeded)
    ops = seeded["ops"]

    await ops.post(f"/orders/{order['id']}/allocate", json={}, expect=200)
    fulfilled = (
        await ops.post(
            f"/orders/{order['id']}/fulfill",
            json={"carrier": "DHL", "tracking_number": "TRK-1"},
            expect=200,
        )
    ).json()
    shipment = fulfilled["fulfillments"][0]
    assert shipment["status"] == "SHIPPED"

    delivered = (
        await ops.post(
            f"/orders/{order['id']}/fulfillments/{shipment['id']}/deliver",
            json={"note": "Signed for at reception."},
            expect=200,
        )
    ).json()
    updated = next(
        f for f in delivered["fulfillments"] if f["id"] == shipment["id"]
    )
    assert updated["status"] == "DELIVERED"
    assert updated["delivered_at"] is not None

    # Confirming twice is a conflict, not a silent success.
    again = await ops.post(
        f"/orders/{order['id']}/fulfillments/{shipment['id']}/deliver", json={}
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "ALREADY_DELIVERED"


async def test_cancelling_an_order_releases_reserved_stock(seeded) -> None:
    """Otherwise an abandoned order locks stock out of every future sale."""
    from tests.test_subscription_lifecycle import _confirmed_order

    order = await _confirmed_order(seeded)
    ops = seeded["ops"]

    await ops.post(f"/orders/{order['id']}/allocate", json={}, expect=200)
    laptop_id = seeded["products"]["HW-LAPTOP-01"]
    reserved = (
        await ops.get("/inventory", params={"product_id": laptop_id}, expect=200)
    ).json()
    assert sum(parse(r["quantity_available"]) for r in reserved) == Decimal("0")

    cancelled = (
        await ops.post(
            f"/orders/{order['id']}/cancel",
            json={"reason": "Customer withdrew the purchase order."},
            expect=200,
        )
    ).json()
    assert cancelled["status"] == "CANCELLED"

    freed = (
        await ops.get("/inventory", params={"product_id": laptop_id}, expect=200)
    ).json()
    assert sum(parse(r["quantity_available"]) for r in freed) == Decimal("100"), (
        "all 100 laptops must return to available stock"
    )


# --------------------------------------------------- nudge and escalate
async def test_acknowledge_nudge_and_escalate(seeded) -> None:
    """PDF B9 — "An automated nudge or escalation action ... from an alert"."""
    sales, manager = seeded["sales"], seeded["manager"]
    built = await build_canonical_quote(seeded)
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    items = page_items(
        (await sales.get("/dashboard/attention-items", expect=200)).json()
    )
    target = next(i for i in items if i["owner_role"] == "MANAGER")
    assert target["status"] == "OPEN"
    assert target["nudge_count"] == 0

    # Anyone internal may nudge — the point is to prod the owner.
    nudged = (
        await sales.post(
            f"/dashboard/attention-items/{target['id']}/nudge",
            json={"note": "Customer is waiting."},
            expect=200,
        )
    ).json()
    assert nudged["notified_role"] == "MANAGER"
    assert nudged["nudge_count"] == 1
    assert "nudged" in nudged["message"]

    # The owner acknowledges: seen and being worked, short of resolved.
    acked = (
        await manager.post(
            f"/dashboard/attention-items/{target['id']}/acknowledge",
            json={"note": "Reviewing today."},
            expect=200,
        )
    ).json()
    assert acked["status"] == "ACKNOWLEDGED"
    assert acked["acknowledged_at"] is not None

    escalated = (
        await sales.post(
            f"/dashboard/attention-items/{target['id']}/escalate",
            json={"note": "Two days with no decision.", "owner_role": "FINANCE"},
            expect=200,
        )
    ).json()
    assert escalated["owner_role"] == "FINANCE"
    assert escalated["escalated_at"] is not None
    assert escalated["escalation_note"] == "Two days with no decision."
    # Severity climbs one band.
    assert escalated["severity"] != target["severity"]


async def test_a_resolved_item_cannot_be_nudged_or_escalated(seeded) -> None:
    sales, manager = seeded["sales"], seeded["manager"]
    built = await build_canonical_quote(seeded)
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    items = page_items(
        (await sales.get("/dashboard/attention-items", expect=200)).json()
    )
    target = next(i for i in items if i["owner_role"] == "MANAGER")
    await manager.post(
        f"/dashboard/attention-items/{target['id']}/resolve",
        json={"resolution_note": "Done."},
        expect=200,
    )

    for action in ("nudge", "escalate"):
        payload = {"note": "still waiting"} if action == "escalate" else {}
        refused = await sales.post(
            f"/dashboard/attention-items/{target['id']}/{action}", json=payload
        )
        assert refused.status_code == 409, action
        assert refused.json()["error"]["code"] == "ITEM_ALREADY_RESOLVED"


async def test_attention_items_can_be_filtered_to_my_queue(seeded) -> None:
    sales, manager = seeded["sales"], seeded["manager"]
    built = await build_canonical_quote(seeded)
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )

    mine = (
        await manager.get(
            "/dashboard/attention-items", params={"mine": True}, expect=200
        )
    ).page()
    assert mine["total"] >= 1
    assert all(i["owner_role"] == "MANAGER" for i in mine["items"])

    by_role = (
        await sales.get(
            "/dashboard/attention-items",
            params={"owner_role": "FINANCE"},
            expect=200,
        )
    ).page()
    assert all(i["owner_role"] == "FINANCE" for i in by_role["items"])
