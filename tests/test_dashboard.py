"""Control Tower and deal health: an action queue, not a KPI wall."""

from __future__ import annotations



from tests.conftest import build_canonical_quote


async def _approve_all(seeded, version_id: str) -> None:
    for approver in (seeded["manager"], seeded["finance"]):
        inbox = (await approver.get("/approvals/inbox", expect=200)).json()
        for item in inbox:
            if str(item["quote_version_id"]) == str(version_id):
                await approver.post(
                    f"/approvals/{item['approval_request_id']}/approve",
                    json={"reason": "ok"},
                    expect=200,
                )


async def test_empty_control_tower_says_so_plainly(seeded) -> None:
    sales = seeded["sales"]
    tower = (await sales.get("/dashboard/control-tower", expect=200)).json()
    assert tower["counts"]["total_open"] == 0
    assert tower["groups"] == []
    assert tower["my_queue"] == []
    assert "Nothing needs your attention" in tower["headline"]


async def test_pending_approval_raises_a_medium_item_owned_by_the_manager(
    seeded,
) -> None:
    built = await build_canonical_quote(seeded)
    sales, manager = seeded["sales"], seeded["manager"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )

    items = (
        await sales.get(
            "/dashboard/attention-items",
            params={"type": "PENDING_APPROVAL"},
            expect=200,
        )
    ).json()
    assert len(items) == 1
    item = items[0]
    assert item["severity"] == "MEDIUM"
    assert item["owner_role"] == "MANAGER"
    assert item["status"] == "OPEN"
    assert item["quote_id"] == built["quote"]["id"]
    assert item["deal_id"] == built["deal"]["id"]
    # The four questions every item must answer.
    assert item["reason"]
    assert item["impact"]
    assert item["recommended_action"]
    assert item["owner_role"]
    assert "132710.00" in item["impact"]

    # It lands in the manager's personal queue, not the sales rep's.
    manager_tower = (await manager.get("/dashboard/control-tower", expect=200)).json()
    assert [i["id"] for i in manager_tower["my_queue"]] == [item["id"]]
    sales_tower = (await sales.get("/dashboard/control-tower", expect=200)).json()
    assert sales_tower["my_queue"] == []


async def test_approval_ownership_moves_to_finance_after_the_manager_approves(
    seeded,
) -> None:
    built = await build_canonical_quote(seeded)
    sales, manager, finance = seeded["sales"], seeded["manager"], seeded["finance"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    inbox = (await manager.get("/approvals/inbox", expect=200)).json()
    await manager.post(
        f"/approvals/{inbox[0]['approval_request_id']}/approve",
        json={"reason": "ok"},
        expect=200,
    )

    items = (
        await sales.get(
            "/dashboard/attention-items",
            params={"type": "PENDING_APPROVAL"},
            expect=200,
        )
    ).json()
    assert len(items) == 1
    assert items[0]["owner_role"] == "FINANCE"
    assert "Sales Manager has approved" in items[0]["impact"]

    finance_tower = (await finance.get("/dashboard/control-tower", expect=200)).json()
    assert len(finance_tower["my_queue"]) == 1


async def test_full_approval_resolves_the_pending_item(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    await _approve_all(seeded, built["version_id"])

    open_items = (await sales.get("/dashboard/attention-items", expect=200)).json()
    assert [i for i in open_items if i["type"] == "PENDING_APPROVAL"] == []

    resolved = (
        await sales.get(
            "/dashboard/attention-items",
            params={"include_resolved": True, "type": "PENDING_APPROVAL"},
            expect=200,
        )
    ).json()
    assert len(resolved) == 1
    assert resolved[0]["status"] == "RESOLVED"
    assert resolved[0]["resolved_at"] is not None


async def test_margin_violation_raises_a_finance_owned_item(seeded) -> None:
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "100", "45"),)
    )
    sales = seeded["sales"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    items = (
        await sales.get(
            "/dashboard/attention-items",
            params={"type": "MARGIN_VIOLATION"},
            expect=200,
        )
    ).json()
    assert len(items) == 1
    assert items[0]["severity"] in ("HIGH", "CRITICAL")
    assert items[0]["owner_role"] == "FINANCE"
    assert "below the required minimum" in items[0]["reason"]
    assert items[0]["detail"]["required_margin_pct"] == "10.0000"


async def test_fixing_the_margin_resolves_the_violation(seeded) -> None:
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "100", "45"),)
    )
    sales = seeded["sales"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    open_items = (
        await sales.get(
            "/dashboard/attention-items",
            params={"type": "MARGIN_VIOLATION"},
            expect=200,
        )
    ).json()
    assert len(open_items) == 1, "the violation must be raised on submit"

    # Revise back inside policy; the alert for that version must close.
    laptop = built["version"]["lines"][0]
    await sales.post(
        f"/quote-versions/{built['version_id']}/revisions",
        json={
            "reason": "pull the discount back to 10%",
            "line_updates": {laptop["id"]: {"discount_pct": "10"}},
        },
        expect=201,
    )
    items = (
        await sales.get(
            "/dashboard/attention-items",
            params={"type": "MARGIN_VIOLATION"},
            expect=200,
        )
    ).json()
    assert items == []


async def test_stale_approval_is_critical_and_blocks_the_order(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales, customer = seeded["sales"], seeded["customer"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    await _approve_all(seeded, built["version_id"])
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
    await customer.post(
        f"/portal/quotes/{built['quote']['id']}/messages",
        json={
            "message_type": "COUNTER_OFFER",
            "body": "25%",
            "lines": [{"quote_line_id": laptop["id"], "requested_discount_pct": "25"}],
        },
        expect=201,
    )

    tower = (await sales.get("/dashboard/control-tower", expect=200)).json()
    by_type = tower["by_type"]
    assert by_type["STALE_APPROVAL"] == 1
    assert by_type["ORDER_BLOCKED"] == 1
    assert tower["counts"]["critical"] >= 2
    assert "Most urgent" in tower["headline"]

    # Severity ordering: critical items come first.
    assert tower["groups"][0]["severity"] == "CRITICAL"
    severities = [g["severity"] for g in tower["groups"]]
    ranks = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    assert [ranks[s] for s in severities] == sorted(
        [ranks[s] for s in severities], reverse=True
    )

    stale = next(
        i
        for i in (await sales.get("/dashboard/attention-items", expect=200)).json()
        if i["type"] == "STALE_APPROVAL"
    )
    assert stale["severity"] == "CRITICAL"
    assert stale["owner_role"] == "FINANCE"
    assert "cannot proceed" in stale["impact"]
    assert "re-approve" in stale["recommended_action"]


async def test_reapproval_clears_the_stale_and_blocked_items(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales, customer = seeded["sales"], seeded["customer"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    await _approve_all(seeded, built["version_id"])
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
                "body": "25%",
                "lines": [
                    {"quote_line_id": laptop["id"], "requested_discount_pct": "25"}
                ],
            },
            expect=201,
        )
    ).json()
    await _approve_all(seeded, counter["new_version_id"])

    items = (await sales.get("/dashboard/attention-items", expect=200)).json()
    types = {i["type"] for i in items}
    assert "STALE_APPROVAL" not in types
    assert "ORDER_BLOCKED" not in types
    assert "PENDING_APPROVAL" not in types


async def test_customer_response_required_appears_after_sending(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    await _approve_all(seeded, built["version_id"])
    await sales.post(
        f"/quote-versions/{built['version_id']}/send", json={}, expect=200
    )

    items = (
        await sales.get(
            "/dashboard/attention-items",
            params={"type": "CUSTOMER_RESPONSE_REQUIRED"},
            expect=200,
        )
    ).json()
    assert len(items) == 1
    assert items[0]["owner_role"] == "SALES"
    assert items[0]["severity"] == "MEDIUM"
    # It lands in the owning rep's personal queue.
    tower = (await sales.get("/dashboard/control-tower", expect=200)).json()
    assert any(i["id"] == items[0]["id"] for i in tower["my_queue"])


async def test_severity_filter_narrows_the_queue(seeded) -> None:
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "100", "45"),)
    )
    sales = seeded["sales"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    high = (
        await sales.get(
            "/dashboard/attention-items", params={"severity": "HIGH"}, expect=200
        )
    ).json()
    assert high
    assert all(i["severity"] == "HIGH" for i in high)
    low = (
        await sales.get(
            "/dashboard/attention-items", params={"severity": "LOW"}, expect=200
        )
    ).json()
    assert low == []


async def test_items_can_be_resolved_manually(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    items = (await sales.get("/dashboard/attention-items", expect=200)).json()
    resolved = (
        await sales.post(
            f"/dashboard/attention-items/{items[0]['id']}/resolve",
            json={"resolution_note": "Handled over the phone."},
            expect=200,
        )
    ).json()
    assert resolved["status"] == "RESOLVED"
    assert resolved["resolved_at"] is not None

    remaining = (await sales.get("/dashboard/attention-items", expect=200)).json()
    assert items[0]["id"] not in {i["id"] for i in remaining}


async def test_editing_a_draft_does_not_spam_the_queue(seeded) -> None:
    """Attention items are raised at decision points, not on every keystroke.

    A draft being priced is not yet asking anyone for anything, so
    recalculating it must not put items in front of an operator.
    """
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "100", "45"),)
    )
    sales = seeded["sales"]
    for _ in range(3):
        await sales.post(
            f"/quote-versions/{built['version_id']}/calculate", expect=200
        )
    items = (await sales.get("/dashboard/attention-items", expect=200)).json()
    assert items == []


async def test_repeated_upserts_refresh_one_item_rather_than_adding(
    seeded,
) -> None:
    """The dedupe guarantee, asserted directly on the service."""
    import uuid

    from sqlalchemy import func, select

    from app.enums import AttentionItemType, RoleCode, Severity
    from app.models.attention_item import AttentionItem
    from app.services.audit_service import AttentionService
    from tests.conftest import db_session

    org_id = uuid.UUID(seeded["seller_organization_id"])
    source_id = uuid.uuid4()

    async with db_session() as s:
        for index, severity in enumerate(
            (Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)
        ):
            await AttentionService.upsert(
                s,
                organization_id=org_id,
                source_type="quote_version",
                source_id=source_id,
                item_type=AttentionItemType.MARGIN_VIOLATION,
                severity=severity,
                title=f"Attempt {index}",
                reason="reason",
                impact="impact",
                owner_role=RoleCode.FINANCE,
                recommended_action="do something",
            )
        await s.commit()

        count = (
            await s.execute(
                select(func.count())
                .select_from(AttentionItem)
                .where(AttentionItem.source_id == source_id)
            )
        ).scalar_one()
        item = (
            await s.execute(
                select(AttentionItem).where(AttentionItem.source_id == source_id)
            )
        ).scalar_one()

    assert int(count) == 1, "upsert must refresh, not duplicate"
    assert item.severity is Severity.CRITICAL, "the latest state must win"
    assert item.title == "Attempt 2"


# ------------------------------------------------------------ deal health
async def test_a_clean_deal_is_healthy(seeded) -> None:
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "5"),)
    )
    sales = seeded["sales"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )

    health = (
        await sales.get(
            f"/dashboard/deal-health/{built['deal']['id']}", expect=200
        )
    ).json()
    assert health["health_score"] == 100
    assert health["health_band"] == "HEALTHY"
    assert health["blocked"] is False
    assert health["open_attention_items"] == 0
    assert health["signals"][0]["code"] == "HEALTHY"
    assert health["customer_name"] == "Acme Corporation"


async def test_health_deducts_for_each_named_problem(seeded) -> None:
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "100", "45"),)
    )
    sales = seeded["sales"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )

    health = (
        await sales.get(
            f"/dashboard/deal-health/{built['deal']['id']}", expect=200
        )
    ).json()
    codes = {s["code"]: s for s in health["signals"]}
    assert "LOW_MARGIN" in codes
    assert "PENDING_APPROVAL" in codes
    assert codes["LOW_MARGIN"]["points"] == -20
    assert codes["PENDING_APPROVAL"]["points"] == -10
    assert health["health_score"] < 100
    assert health["blocked"] is True
    # The score is exactly 100 plus the deductions — nothing hand-waved.
    assert health["health_score"] == max(
        0, 100 + sum(s["points"] for s in health["signals"])
    )
    assert health["summary"]


async def test_stale_approval_drops_health_and_marks_it_blocked(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales, customer = seeded["sales"], seeded["customer"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    await _approve_all(seeded, built["version_id"])
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
    await customer.post(
        f"/portal/quotes/{built['quote']['id']}/messages",
        json={
            "message_type": "COUNTER_OFFER",
            "body": "25%",
            "lines": [{"quote_line_id": laptop["id"], "requested_discount_pct": "25"}],
        },
        expect=201,
    )

    health = (
        await sales.get(
            f"/dashboard/deal-health/{built['deal']['id']}", expect=200
        )
    ).json()
    codes = {s["code"] for s in health["signals"]}
    assert "STALE_APPROVAL" in codes
    assert health["blocked"] is True
    assert health["health_band"] in ("AT_RISK", "CRITICAL", "WATCH")


async def test_confirmed_deal_scores_one_hundred(seeded) -> None:
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "5"),)
    )
    sales, customer = seeded["sales"], seeded["customer"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    await sales.post(
        f"/quote-versions/{built['version_id']}/send", json={}, expect=200
    )
    await customer.post(
        f"/portal/quotes/{built['quote']['id']}/confirm", json={}, expect=200
    )

    health = (
        await sales.get(
            f"/dashboard/deal-health/{built['deal']['id']}", expect=200
        )
    ).json()
    assert health["stage"] == "CLOSED_WON"
    assert health["health_score"] == 100
    assert health["signals"][0]["code"] == "CLOSED_WON"


async def test_deal_health_list_is_sorted_worst_first(seeded) -> None:
    sales = seeded["sales"]
    healthy = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "5"),), title="Healthy deal"
    )
    sick = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "100", "45"),), title="Sick deal"
    )
    await sales.post(
        f"/quote-versions/{healthy['version_id']}/submit", json={}, expect=200
    )
    await sales.post(
        f"/quote-versions/{sick['version_id']}/submit", json={}, expect=200
    )

    body = (await sales.get("/dashboard/deal-health", expect=200)).json()
    assert len(body["deals"]) == 2
    scores = [d["health_score"] for d in body["deals"]]
    assert scores == sorted(scores), "worst deals must surface first"
    assert body["deals"][0]["deal_name"] == "Sick deal"
    assert 0 <= body["average_health"] <= 100


async def test_a_deal_with_no_quote_loses_points(seeded) -> None:
    sales = seeded["sales"]
    deal = (
        await sales.post(
            "/deals",
            json={
                "name": "Idle deal",
                "customer_profile_id": seeded["customer_profile_id"],
            },
            expect=201,
        )
    ).json()
    health = (
        await sales.get(f"/dashboard/deal-health/{deal['id']}", expect=200)
    ).json()
    codes = {s["code"] for s in health["signals"]}
    assert "NO_QUOTE" in codes
    assert health["health_score"] == 90
