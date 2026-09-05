"""Approval workflow: routing, ordered steps, decisions, self-approval ban."""

from __future__ import annotations

import uuid
from decimal import Decimal


from tests.conftest import build_canonical_quote, db_session, login, money as parse


async def _submit(seeded, version_id: str) -> dict:
    sales = seeded["sales"]
    return (
        await sales.post(f"/quote-versions/{version_id}/submit", json={}, expect=200)
    ).json()


async def _inbox_item(approver, version_id: str) -> dict | None:
    inbox = (await approver.get("/approvals/inbox", expect=200)).json()
    return next(
        (i for i in inbox if str(i["quote_version_id"]) == str(version_id)), None
    )


# ---------------------------------------------------------------- routing
async def test_submit_creates_approval_automatically(seeded) -> None:
    """Sales never has to ask for approval — submitting is enough."""
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await _submit(seeded, built["version_id"])

    version = (
        await sales.get(f"/quote-versions/{built['version_id']}", expect=200)
    ).json()
    assert version["status"] == "PENDING_APPROVAL"
    assert version["requires_approval"] is True
    assert version["submitted_at"] is not None

    approval = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/approval", expect=200
        )
    ).json()["approval_request"]
    assert approval["status"] == "PENDING"
    assert [s["level"] for s in approval["steps"]] == ["SALES_MANAGER", "FINANCE"]
    assert [s["required_role"] for s in approval["steps"]] == ["MANAGER", "FINANCE"]
    assert approval["current_step_sequence"] == 1


async def test_only_manager_step_when_only_a_ceiling_is_breached(seeded) -> None:
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "18"),)
    )
    sales = seeded["sales"]
    await _submit(seeded, built["version_id"])
    approval = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/approval", expect=200
        )
    ).json()["approval_request"]
    assert [s["level"] for s in approval["steps"]] == ["SALES_MANAGER"]


async def test_inbox_only_shows_the_current_step_for_your_role(seeded) -> None:
    built = await build_canonical_quote(seeded)
    manager, finance = seeded["manager"], seeded["finance"]
    await _submit(seeded, built["version_id"])

    assert await _inbox_item(manager, built["version_id"]) is not None
    # Finance is step 2; it must not appear until the manager has decided.
    assert await _inbox_item(finance, built["version_id"]) is None


async def test_ordered_steps_manager_then_finance(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales, manager, finance = seeded["sales"], seeded["manager"], seeded["finance"]
    await _submit(seeded, built["version_id"])

    item = await _inbox_item(manager, built["version_id"])
    assert item is not None
    assert item["level"] == "SALES_MANAGER"
    assert item["is_reapproval"] is False
    assert parse(item["total_revenue"]) == Decimal("132710.00")
    assert parse(item["blended_risk_score"]) > Decimal("0")

    response = (
        await manager.post(
            f"/approvals/{item['approval_request_id']}/approve",
            json={"reason": "Volume justifies the extra 3 points."},
            expect=200,
        )
    ).json()
    assert "Now awaiting Finance approval" in response["message"]
    assert response["quote_version_status"] == "PENDING_APPROVAL"

    # Now, and only now, Finance sees it.
    finance_item = await _inbox_item(finance, built["version_id"])
    assert finance_item is not None
    assert finance_item["level"] == "FINANCE"

    final = (
        await finance.post(
            f"/approvals/{finance_item['approval_request_id']}/approve",
            json={"reason": "Margin 24.5% is comfortable."},
            expect=200,
        )
    ).json()
    assert final["quote_version_status"] == "APPROVED"
    assert "fully approved" in final["message"]

    version = (
        await sales.get(f"/quote-versions/{built['version_id']}", expect=200)
    ).json()
    assert version["status"] == "APPROVED"
    assert version["approved_at"] is not None


async def test_finance_cannot_jump_the_queue(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales, finance = seeded["sales"], seeded["finance"]
    await _submit(seeded, built["version_id"])
    approval = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/approval", expect=200
        )
    ).json()["approval_request"]

    response = await finance.post(
        f"/approvals/{approval['id']}/approve", json={"reason": "me first"}
    )
    assert response.status_code == 403
    body = response.json()["error"]
    assert body["code"] == "WRONG_APPROVER_ROLE"
    assert body["details"]["required_role"] == "MANAGER"
    assert body["details"]["your_role"] == "FINANCE"


# --------------------------------------------------------- self-approval
async def test_sales_cannot_reach_approval_endpoints_at_all(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await _submit(seeded, built["version_id"])
    approval = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/approval", expect=200
        )
    ).json()["approval_request"]

    for action in ("approve", "reject", "request-revision"):
        response = await sales.post(
            f"/approvals/{approval['id']}/{action}", json={"reason": "me"}
        )
        assert response.status_code == 403, action
        assert response.json()["error"]["code"] == "FORBIDDEN"

    inbox = await sales.get("/approvals/inbox")
    assert inbox.status_code == 403


async def test_a_manager_cannot_approve_a_quote_they_raised(seeded, client) -> None:
    """The critical invariant: role alone is not enough — authorship blocks it."""
    admin = seeded["admin"]
    await admin.post(
        "/users",
        json={
            "email": "player.coach@techsupply.com",
            "password": seeded["password"],
            "full_name": "Player Coach",
            "role": "MANAGER",
        },
        expect=201,
    )
    coach = await login(client, "player.coach@techsupply.com", seeded["password"])

    deal = (
        await coach.post(
            "/deals",
            json={
                "name": "Manager-owned deal",
                "customer_profile_id": seeded["customer_profile_id"],
            },
            expect=201,
        )
    ).json()
    quote = (
        await coach.post(
            f"/deals/{deal['id']}/quotes",
            json={
                "title": "Manager-owned",
                "lines": [
                    {
                        "product_id": seeded["products"]["HW-LAPTOP-01"],
                        "quantity": "10",
                        "discount_pct": "18",
                    }
                ],
            },
            expect=201,
        )
    ).json()
    version_id = quote["current_version_id"]
    await coach.post(f"/quote-versions/{version_id}/submit", json={}, expect=200)

    approval = (
        await coach.get(f"/quote-versions/{version_id}/approval", expect=200)
    ).json()["approval_request"]

    response = await coach.post(
        f"/approvals/{approval['id']}/approve", json={"reason": "rubber stamp"}
    )
    assert response.status_code == 403
    body = response.json()["error"]
    assert body["code"] == "SELF_APPROVAL_FORBIDDEN"
    assert "quote you created or submitted" in body["message"]

    # It must not even appear in their inbox — it is not actionable.
    assert await _inbox_item(coach, version_id) is None

    # A different manager can approve it.
    other = seeded["manager"]
    item = await _inbox_item(other, version_id)
    assert item is not None
    await other.post(
        f"/approvals/{item['approval_request_id']}/approve",
        json={"reason": "independent review"},
        expect=200,
    )


# ------------------------------------------------------------- decisions
async def test_a_decided_step_cannot_be_decided_twice(seeded) -> None:
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "18"),)
    )
    manager = seeded["manager"]
    await _submit(seeded, built["version_id"])
    item = await _inbox_item(manager, built["version_id"])
    assert item is not None

    await manager.post(
        f"/approvals/{item['approval_request_id']}/approve",
        json={"reason": "first decision"},
        expect=200,
    )
    response = await manager.post(
        f"/approvals/{item['approval_request_id']}/approve",
        json={"reason": "second decision"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPROVAL_NOT_PENDING"


async def test_rejection_makes_the_version_immutable_forever(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales, manager = seeded["sales"], seeded["manager"]
    await _submit(seeded, built["version_id"])
    item = await _inbox_item(manager, built["version_id"])

    response = (
        await manager.post(
            f"/approvals/{item['approval_request_id']}/reject",
            json={"reason": "Discount is indefensible at this volume."},
            expect=200,
        )
    ).json()
    assert response["quote_version_status"] == "REJECTED"

    version = (
        await sales.get(f"/quote-versions/{built['version_id']}", expect=200)
    ).json()
    assert version["status"] == "REJECTED"
    assert version["rejected_at"] is not None

    # Cannot edit, cannot revise.
    line = version["lines"][0]
    patch = await sales.patch(
        f"/quote-versions/{built['version_id']}/lines/{line['id']}",
        json={"discount_pct": "5"},
    )
    assert patch.status_code == 409
    revise = await sales.post(
        f"/quote-versions/{built['version_id']}/revisions", json={"reason": "retry"}
    )
    assert revise.status_code == 409
    assert revise.json()["error"]["code"] == "VERSION_TERMINAL"


async def test_rejection_skips_the_remaining_steps(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales, manager, finance = seeded["sales"], seeded["manager"], seeded["finance"]
    await _submit(seeded, built["version_id"])
    item = await _inbox_item(manager, built["version_id"])
    await manager.post(
        f"/approvals/{item['approval_request_id']}/reject",
        json={"reason": "no"},
        expect=200,
    )
    detail = (
        await sales.get(f"/approvals/{item['approval_request_id']}", expect=200)
    ).json()
    statuses = {s["level"]: s["status"] for s in detail["steps"]}
    assert statuses["SALES_MANAGER"] == "REJECTED"
    assert statuses["FINANCE"] == "SKIPPED"
    assert await _inbox_item(finance, built["version_id"]) is None


async def test_request_revision_returns_the_version_to_draft(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales, manager = seeded["sales"], seeded["manager"]
    await _submit(seeded, built["version_id"])
    item = await _inbox_item(manager, built["version_id"])

    response = (
        await manager.post(
            f"/approvals/{item['approval_request_id']}/request-revision",
            json={"reason": "Bring the laptop discount back to 15%."},
            expect=200,
        )
    ).json()
    assert response["quote_version_status"] == "DRAFT"

    version = (
        await sales.get(f"/quote-versions/{built['version_id']}", expect=200)
    ).json()
    assert version["status"] == "DRAFT"
    assert version["is_editable"] is True
    assert version["submitted_at"] is None

    # Sales can now fix it in place and resubmit.
    laptop = next(
        line for line in version["lines"] if "Laptop" in line["description"]
    )
    await sales.patch(
        f"/quote-versions/{built['version_id']}/lines/{laptop['id']}",
        json={"discount_pct": "15"},
        expect=200,
    )
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )


async def test_every_decision_records_actor_reason_and_the_numbers(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales, manager, finance = seeded["sales"], seeded["manager"], seeded["finance"]
    await _submit(seeded, built["version_id"])

    item = await _inbox_item(manager, built["version_id"])
    await manager.post(
        f"/approvals/{item['approval_request_id']}/approve",
        json={"reason": "Manager rationale here."},
        expect=200,
    )
    finance_item = await _inbox_item(finance, built["version_id"])
    await finance.post(
        f"/approvals/{finance_item['approval_request_id']}/approve",
        json={"reason": "Finance rationale here."},
        expect=200,
    )

    detail = (
        await sales.get(f"/approvals/{item['approval_request_id']}", expect=200)
    ).json()
    assert len(detail["decisions"]) == 2
    for decision in detail["decisions"]:
        assert decision["actor_email"]
        assert decision["actor_role"] in ("MANAGER", "FINANCE")
        assert decision["reason"]
        assert decision["decided_at"]
        snapshot = decision["decision_snapshot"]
        assert snapshot["margin_pct"] == "24.4970"
        assert snapshot["total_revenue"] == "132710.00"
        assert snapshot["blended_risk_score"]

    assert detail["financials"]["net_revenue"] == "132710.00"
    assert detail["financials"]["total_cost"] == "100200.00"


async def test_approval_clears_staleness_and_unblocks_confirmation(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales, manager, finance = seeded["sales"], seeded["manager"], seeded["finance"]

    # Approve v1.
    await _submit(seeded, built["version_id"])
    for approver in (manager, finance):
        item = await _inbox_item(approver, built["version_id"])
        await approver.post(
            f"/approvals/{item['approval_request_id']}/approve",
            json={"reason": "ok"},
            expect=200,
        )

    # Material revision -> v1's approval goes stale, v2 needs re-approval.
    laptop = next(
        line for line in built["version"]["lines"] if "Laptop" in line["description"]
    )
    v2 = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={
                "reason": "counter at 25%",
                "line_updates": {laptop["id"]: {"discount_pct": "25"}},
            },
            expect=201,
        )
    ).json()
    assert v2["is_stale"] is True

    # Re-approve v2.
    for approver in (manager, finance):
        item = await _inbox_item(approver, v2["id"])
        assert item is not None, "re-approval must be routed to both levels"
        assert item["is_reapproval"] is True
        await approver.post(
            f"/approvals/{item['approval_request_id']}/approve",
            json={"reason": "re-approved after counter"},
            expect=200,
        )

    refreshed = (await sales.get(f"/quote-versions/{v2['id']}", expect=200)).json()
    assert refreshed["status"] == "APPROVED"
    assert refreshed["is_stale"] is False
    assert refreshed["stale_reason"] is None


async def test_pending_request_on_a_superseded_version_is_cancelled(seeded) -> None:
    """No decision was ever made, so it is cancelled rather than made stale."""
    from sqlalchemy import select

    from app.models.approval_request import ApprovalRequest

    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await _submit(seeded, built["version_id"])

    laptop = next(
        line for line in built["version"]["lines"] if "Laptop" in line["description"]
    )
    await sales.post(
        f"/quote-versions/{built['version_id']}/revisions",
        json={
            "reason": "changed our mind before approval",
            "line_updates": {laptop["id"]: {"discount_pct": "20"}},
        },
        expect=201,
    )

    async with db_session() as s:
        requests = list(
            (
                await s.execute(
                    select(ApprovalRequest).where(
                        ApprovalRequest.quote_version_id
                        == uuid.UUID(built["version_id"])
                    )
                )
            ).scalars()
        )
    assert len(requests) == 1
    assert requests[0].status.value == "CANCELLED"
    assert "Superseded by version 2" in requests[0].stale_reason


async def test_admin_can_act_on_any_step(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales, admin = seeded["sales"], seeded["admin"]
    await _submit(seeded, built["version_id"])
    approval = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/approval", expect=200
        )
    ).json()["approval_request"]

    await admin.post(
        f"/approvals/{approval['id']}/approve",
        json={"reason": "admin override, documented"},
        expect=200,
    )
    await admin.post(
        f"/approvals/{approval['id']}/approve",
        json={"reason": "admin override, finance step"},
        expect=200,
    )
    version = (
        await sales.get(f"/quote-versions/{built['version_id']}", expect=200)
    ).json()
    assert version["status"] == "APPROVED"


async def test_approval_request_from_another_org_is_not_found(seeded, client) -> None:
    from tests.conftest import signup

    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await _submit(seeded, built["version_id"])
    approval = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/approval", expect=200
        )
    ).json()["approval_request"]

    await signup(
        client,
        email="rival.manager@rival.dev",
        full_name="Rival Manager",
        role="MANAGER",
        organization_name="Rival Supplies",
    )
    rival = await login(client, "rival.manager@rival.dev")

    read = await rival.get(f"/approvals/{approval['id']}")
    assert read.status_code == 404
    act = await rival.post(
        f"/approvals/{approval['id']}/approve", json={"reason": "not mine"}
    )
    assert act.status_code == 404


async def test_approval_reason_is_required(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales, manager = seeded["sales"], seeded["manager"]
    await _submit(seeded, built["version_id"])
    approval = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/approval", expect=200
        )
    ).json()["approval_request"]

    for payload in ({}, {"reason": ""}, {"reason": "   "}):
        response = await manager.post(
            f"/approvals/{approval['id']}/approve", json=payload
        )
        assert response.status_code == 422, payload
