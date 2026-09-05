"""DecisionFabric: material change detection, staleness, explainability."""

from __future__ import annotations

import uuid


from app.enums import Severity
from app.services.decision_fabric import DecisionFabric
from tests.conftest import build_canonical_quote, db_session


async def _submit_and_approve(seeded, version_id: str) -> dict:
    """Drive a quote to APPROVED through the real approval workflow."""
    sales, manager, finance = seeded["sales"], seeded["manager"], seeded["finance"]
    await sales.post(f"/quote-versions/{version_id}/submit", json={}, expect=200)

    for approver in (manager, finance):
        inbox = (await approver.get("/approvals/inbox", expect=200)).json()
        for item in inbox:
            if str(item["quote_version_id"]) == str(version_id):
                await approver.post(
                    f"/approvals/{item['approval_request_id']}/approve",
                    json={"reason": "approved for test"},
                    expect=200,
                )
    return (await sales.get(f"/quote-versions/{version_id}", expect=200)).json()


def _impact_fields(payload: dict) -> set[str]:
    return {c["field"] for c in payload["material_changes"]}


# ------------------------------------------------------ pure change detection
def test_no_previous_version_means_no_changes() -> None:
    assert (
        DecisionFabric.detect_changes(
            previous=None,
            previous_lines=[],
            current=object(),  # never touched when previous is None
            current_lines=[],
        )
        == []
    )


# ------------------------------------------------------------ initial submit
async def test_impact_on_first_submit_reports_no_changes(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    payload = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
        )
    ).json()

    assert payload["changes"] == []
    assert payload["material_changes"] == []
    assert payload["has_material_change"] is False
    assert payload["stale_decisions"] == []
    assert payload["policy_results"], "policy must still be evaluated"
    assert payload["required_approvals"], "the demo quote needs approval"
    explanation = payload["explanation"]
    assert explanation["summary"]
    assert explanation["what_changed"]
    assert explanation["why_it_matters"]
    assert explanation["who_is_affected"]
    assert explanation["what_happens_next"]


# ------------------------------------------------- material change detection
async def test_discount_change_is_material_and_explained(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    laptop = next(
        line for line in built["version"]["lines"] if "Laptop" in line["description"]
    )
    new_version = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={
                "reason": "customer pushed for 25%",
                "line_updates": {laptop["id"]: {"discount_pct": "25"}},
            },
            expect=201,
        )
    ).json()

    payload = (
        await sales.get(f"/quote-versions/{new_version['id']}/impact", expect=200)
    ).json()
    assert payload["has_material_change"] is True
    fields = _impact_fields(payload)
    assert "discount_pct" in fields

    change = next(
        c for c in payload["material_changes"] if c["field"] == "discount_pct"
    )
    assert change["old"] == "18.0000"
    assert change["new"] == "25.0000"
    assert change["severity"] == Severity.HIGH.value  # 7 points >= 5
    assert "increased from 18% to 25%" in change["reason"]
    assert "category ceiling" in change["reason"]


async def test_quantity_change_is_material(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    laptop = next(
        line for line in built["version"]["lines"] if "Laptop" in line["description"]
    )
    new_version = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={
                "reason": "scaled down",
                "line_updates": {laptop["id"]: {"quantity": "40"}},
            },
            expect=201,
        )
    ).json()
    payload = (
        await sales.get(f"/quote-versions/{new_version['id']}/impact", expect=200)
    ).json()
    change = next(c for c in payload["material_changes"] if c["field"] == "quantity")
    assert change["old"] == "100.0000"
    assert change["new"] == "40.0000"
    assert change["severity"] == Severity.HIGH.value  # 60% swing
    assert "stock that must be allocated" in change["reason"]


async def test_unit_price_change_is_material(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    laptop = next(
        line for line in built["version"]["lines"] if "Laptop" in line["description"]
    )
    new_version = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={
                "reason": "special pricing",
                "line_updates": {laptop["id"]: {"unit_list_price": "1100"}},
            },
            expect=201,
        )
    ).json()
    payload = (
        await sales.get(f"/quote-versions/{new_version['id']}/impact", expect=200)
    ).json()
    assert "unit_price" in _impact_fields(payload)


async def test_margin_change_is_material_and_crossing_the_floor_is_critical(
    seeded,
) -> None:
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "100", "10"),)
    )
    sales = seeded["sales"]
    laptop = built["version"]["lines"][0]
    # 10% -> 40% takes margin from 25.9% to below the 10% floor.
    new_version = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={
                "reason": "deep discount",
                "line_updates": {laptop["id"]: {"discount_pct": "40"}},
            },
            expect=201,
        )
    ).json()
    payload = (
        await sales.get(f"/quote-versions/{new_version['id']}/impact", expect=200)
    ).json()

    margin_change = next(
        c for c in payload["material_changes"] if c["field"] == "margin_pct"
    )
    assert margin_change["severity"] == Severity.CRITICAL.value
    assert "crosses the 10% minimum margin floor" in margin_change["reason"]


async def test_payment_terms_change_is_material(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    new_version = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={"reason": "extended terms", "payment_terms": "NET_60"},
            expect=201,
        )
    ).json()
    payload = (
        await sales.get(f"/quote-versions/{new_version['id']}/impact", expect=200)
    ).json()
    change = next(
        c for c in payload["material_changes"] if c["field"] == "payment_terms"
    )
    assert change["old"] == "NET_30"
    assert change["new"] == "NET_60"
    assert "cash-flow exposure" in change["reason"]


async def test_added_and_removed_lines_are_material(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    support = next(
        line for line in built["version"]["lines"] if "Support" in line["description"]
    )
    new_version = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={
                "reason": "swap support for extra monitors",
                "remove_line_ids": [support["id"]],
                "add_lines": [
                    {
                        "product_id": seeded["products"]["HW-MONITOR-27"],
                        "quantity": "10",
                        "discount_pct": "0",
                    }
                ],
            },
            expect=201,
        )
    ).json()
    payload = (
        await sales.get(f"/quote-versions/{new_version['id']}/impact", expect=200)
    ).json()
    fields = _impact_fields(payload)
    assert "line_removed" in fields
    assert "line_added" in fields


async def test_description_only_change_is_recorded_but_not_material(seeded) -> None:
    """The Fabric must be able to say 'we looked at this and it didn't matter'."""
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    laptop = next(
        line for line in built["version"]["lines"] if "Laptop" in line["description"]
    )
    new_version = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={
                "reason": "tidy up wording",
                "line_updates": {
                    laptop["id"]: {"description": "Business Laptop (14-inch)"}
                },
            },
            expect=201,
        )
    ).json()
    payload = (
        await sales.get(f"/quote-versions/{new_version['id']}/impact", expect=200)
    ).json()

    assert payload["has_material_change"] is False
    assert payload["stale_decisions"] == []
    recorded = {c["field"] for c in payload["changes"]}
    assert "description" in recorded
    change = next(c for c in payload["changes"] if c["field"] == "description")
    assert change["material"] is False


async def test_approval_routing_change_is_itself_a_material_change(seeded) -> None:
    """Going from Manager-only to Manager+Finance must be recorded as a change."""
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "18"),)
    )
    sales = seeded["sales"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )
    laptop = built["version"]["lines"][0]

    # Scale up so total discount crosses the 20,000 Finance authority limit.
    new_version = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={
                "reason": "scale to 100 units",
                "line_updates": {laptop["id"]: {"quantity": "100"}},
            },
            expect=201,
        )
    ).json()
    payload = (
        await sales.get(f"/quote-versions/{new_version['id']}/impact", expect=200)
    ).json()

    change = next(
        c for c in payload["material_changes"] if c["field"] == "required_approvals"
    )
    assert change["old"] == ["SALES_MANAGER"]
    assert set(change["new"]) == {"SALES_MANAGER", "FINANCE"}
    assert "now also requires FINANCE" in change["reason"]


# ------------------------------------------------------------- staleness
async def test_material_revision_marks_the_previous_approval_stale(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    approved = await _submit_and_approve(seeded, built["version_id"])
    assert approved["status"] == "APPROVED"

    laptop = next(
        line for line in approved["lines"] if "Laptop" in line["description"]
    )
    new_version = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={
                "reason": "customer countered at 25%",
                "line_updates": {laptop["id"]: {"discount_pct": "25"}},
            },
            expect=201,
        )
    ).json()

    payload = (
        await sales.get(f"/quote-versions/{new_version['id']}/impact", expect=200)
    ).json()

    assert payload["has_material_change"] is True
    assert len(payload["stale_decisions"]) == 1
    stale = payload["stale_decisions"][0]
    assert stale["previous_decision"] == "APPROVED"
    assert "no longer valid" in stale["reason"]

    assert payload["blocks_confirmation"] is True
    assert new_version["is_stale"] is True
    assert new_version["stale_reason"]

    # A brand new approval request must exist and be routed.
    assert payload["required_approvals"], "re-approval must be routed"
    assert any(
        e["type"] == "approval_request" for e in payload["affected_entities"]
    )

    # And a CRITICAL attention item must be raised for the owner.
    stale_items = [
        i for i in payload["attention_items"] if i["type"] == "STALE_APPROVAL"
    ]
    assert stale_items
    assert stale_items[0]["severity"] == "CRITICAL"
    assert stale_items[0]["owner_role"] == "FINANCE"
    assert stale_items[0]["recommended_action"]


async def test_immaterial_revision_does_not_invalidate_the_approval(seeded) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    approved = await _submit_and_approve(seeded, built["version_id"])
    laptop = next(
        line for line in approved["lines"] if "Laptop" in line["description"]
    )

    new_version = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={
                "reason": "typo fix only",
                "line_updates": {laptop["id"]: {"notes": "confirmed spec with IT"}},
            },
            expect=201,
        )
    ).json()
    payload = (
        await sales.get(f"/quote-versions/{new_version['id']}/impact", expect=200)
    ).json()
    assert payload["has_material_change"] is False
    assert payload["stale_decisions"] == []
    assert new_version["is_stale"] is False


async def test_stale_approval_is_recorded_not_deleted(seeded) -> None:
    """History must survive: the old APPROVED decision stays on the record."""
    from sqlalchemy import select

    from app.models.approval_decision import ApprovalDecision
    from app.models.approval_request import ApprovalRequest

    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await _submit_and_approve(seeded, built["version_id"])
    laptop = next(
        line for line in built["version"]["lines"] if "Laptop" in line["description"]
    )
    await sales.post(
        f"/quote-versions/{built['version_id']}/revisions",
        json={
            "reason": "counter",
            "line_updates": {laptop["id"]: {"discount_pct": "25"}},
        },
        expect=201,
    )

    async with db_session() as s:
        requests = list(
            (
                await s.execute(
                    select(ApprovalRequest).where(
                        ApprovalRequest.quote_id == uuid.UUID(built["quote"]["id"])
                    )
                )
            ).scalars()
        )
        decisions = list((await s.execute(select(ApprovalDecision))).scalars())

    statuses = {r.status.value for r in requests}
    assert "STALE" in statuses, "the old approval must be marked, not removed"
    assert "PENDING" in statuses, "a fresh approval must exist"
    stale = next(r for r in requests if r.status.value == "STALE")
    assert stale.stale_at is not None
    assert stale.stale_reason
    assert stale.superseded_by_request_id is not None
    # Every original decision is still there with actor and reason.
    assert decisions
    for decision in decisions:
        assert decision.actor_email
        assert decision.reason
        assert decision.decided_at is not None
        assert decision.decision_snapshot["margin_pct"]


async def test_decision_impacts_are_persisted(seeded) -> None:
    from sqlalchemy import select

    from app.models.decision_impact import DecisionImpact

    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await _submit_and_approve(seeded, built["version_id"])
    laptop = next(
        line for line in built["version"]["lines"] if "Laptop" in line["description"]
    )
    new_version = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={
                "reason": "counter",
                "line_updates": {laptop["id"]: {"discount_pct": "25"}},
            },
            expect=201,
        )
    ).json()

    async with db_session() as s:
        impacts = list(
            (
                await s.execute(
                    select(DecisionImpact).where(
                        DecisionImpact.quote_version_id == uuid.UUID(new_version["id"])
                    )
                )
            ).scalars()
        )

    assert impacts, "decision_impacts must be written"
    assert any(i.material for i in impacts)
    discount = next(i for i in impacts if i.changed_field == "discount_pct")
    assert discount.old_value == "18.0000"
    assert discount.new_value == "25.0000"
    assert discount.previous_version_id == uuid.UUID(built["version_id"])
    assert discount.change_reason
    assert discount.action_required == "REEVALUATE_POLICY"


async def test_explanation_builds_a_real_causal_chain(seeded) -> None:
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "100", "10"),)
    )
    sales = seeded["sales"]
    await _submit_and_approve(seeded, built["version_id"])
    laptop = built["version"]["lines"][0]

    new_version = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/revisions",
            json={
                "reason": "customer countered at 40%",
                "line_updates": {laptop["id"]: {"discount_pct": "40"}},
            },
            expect=201,
        )
    ).json()
    payload = (
        await sales.get(f"/quote-versions/{new_version['id']}/impact", expect=200)
    ).json()

    explanation = payload["explanation"]
    chain = " | ".join(explanation["causal_chain"])
    assert "discount_pct" in chain or "Discount" in chain
    assert "margin_pct" in chain or "Margin" in chain
    assert "MIN_MARGIN violated" in chain
    assert "STALE" in chain
    assert explanation["summary"]
    assert "confirmation is blocked" in explanation["what_happens_next"].lower()


async def test_fabric_runs_on_every_revision_without_exception(seeded) -> None:
    """Three consecutive revisions must each leave a full evaluation behind."""
    from sqlalchemy import func, select

    from app.models.policy_result import PolicyResult

    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    current = built["version_id"]
    version_ids = [current]

    for index in range(3):
        new_version = (
            await sales.post(
                f"/quote-versions/{current}/revisions",
                json={"reason": f"revision {index}"},
                expect=201,
            )
        ).json()
        current = new_version["id"]
        version_ids.append(current)

    async with db_session() as s:
        for version_id in version_ids:
            count = (
                await s.execute(
                    select(func.count())
                    .select_from(PolicyResult)
                    .where(PolicyResult.quote_version_id == uuid.UUID(version_id))
                )
            ).scalar_one()
            assert int(count) > 0, f"version {version_id} was never evaluated"


async def test_impact_endpoint_is_a_pure_read(seeded) -> None:
    """Calling impact repeatedly must not create new impacts or approvals."""
    from sqlalchemy import func, select

    from app.models.approval_request import ApprovalRequest
    from app.models.decision_impact import DecisionImpact

    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )

    async def counts() -> tuple[int, int]:
        async with db_session() as s:
            impacts = (
                await s.execute(select(func.count()).select_from(DecisionImpact))
            ).scalar_one()
            requests = (
                await s.execute(select(func.count()).select_from(ApprovalRequest))
            ).scalar_one()
            return int(impacts), int(requests)

    before = await counts()
    for _ in range(3):
        await sales.get(f"/quote-versions/{built['version_id']}/impact", expect=200)
    assert await counts() == before
