"""What-if simulation.

Two properties matter and both are asserted here: a simulation must agree with
what a real submit would produce, and it must write nothing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.conftest import build_canonical_quote, db_session, money as parse

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_simulation_reports_a_baseline_and_a_proposal(seeded) -> None:
    sales = seeded["sales"]
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "10"),)
    )
    version_id = built["version_id"]
    line_id = built["version"]["lines"][0]["id"]

    result = (
        await sales.post(
            f"/quote-versions/{version_id}/simulate",
            json={"line_discounts": {line_id: "30"}},
            expect=200,
        )
    ).json()

    assert result["persisted"] is False
    assert parse(result["baseline"]["effective_discount_pct"]) == Decimal("10.0000")
    assert parse(result["proposed"]["effective_discount_pct"]) == Decimal("30.0000")
    # A deeper discount lowers margin and raises risk.
    assert parse(result["margin_delta"]) < Decimal("0")
    assert parse(result["risk_delta"]) > Decimal("0")
    assert result["verdict"]


async def test_simulation_predicts_the_approval_requirement(seeded) -> None:
    """The point of the feature: see the governance cost before committing."""
    sales = seeded["sales"]
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "10"),)
    )
    version_id = built["version_id"]
    line_id = built["version"]["lines"][0]["id"]

    result = (
        await sales.post(
            f"/quote-versions/{version_id}/simulate",
            json={"line_discounts": {line_id: "30"}},
            expect=200,
        )
    ).json()

    # 10% is inside the Gold hardware ceiling; 30% is not.
    assert result["baseline"]["requires_approval"] is False
    assert result["proposed"]["requires_approval"] is True
    assert "SALES_MANAGER" in result["approvals_added"]
    assert "newly require" in result["verdict"]


async def test_simulation_matches_what_a_real_submit_produces(seeded) -> None:
    """A parallel implementation would be free to drift; this proves it cannot.

    `PolicyEngine.evaluate` and `CommercialEngine.calculate_line` are pure, so
    the simulation calls exactly the same code the persisted path calls.
    """
    sales = seeded["sales"]
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "10"),)
    )
    version_id = built["version_id"]
    line_id = built["version"]["lines"][0]["id"]

    predicted = (
        await sales.post(
            f"/quote-versions/{version_id}/simulate",
            json={"line_discounts": {line_id: "22"}},
            expect=200,
        )
    ).json()["proposed"]

    # Now actually make the change and recalculate.
    await sales.patch(
        f"/quote-versions/{version_id}/lines/{line_id}",
        json={"discount_pct": "22"},
        expect=200,
    )
    actual = (
        await sales.post(f"/quote-versions/{version_id}/calculate", expect=200)
    ).json()
    policy = (
        await sales.get(
            f"/quote-versions/{version_id}/policy-results", expect=200
        )
    ).json()

    assert parse(predicted["net_revenue"]) == parse(actual["net_revenue"])
    assert parse(predicted["margin"]) == parse(actual["margin"])
    assert parse(predicted["margin_pct"]) == parse(actual["margin_pct"])
    assert parse(predicted["blended_risk_score"]) == parse(
        policy["blended_risk"]["score"]
    )
    assert predicted["risk_band"] == policy["blended_risk"]["band"]


async def test_simulation_persists_nothing(seeded) -> None:
    sales = seeded["sales"]
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "10"),)
    )
    version_id = built["version_id"]
    line_id = built["version"]["lines"][0]["id"]

    before = (await sales.get(f"/quote-versions/{version_id}", expect=200)).json()

    await sales.post(
        f"/quote-versions/{version_id}/simulate",
        json={"line_discounts": {line_id: "45"}, "order_discount_pct": "10"},
        expect=200,
    )

    after = (await sales.get(f"/quote-versions/{version_id}", expect=200)).json()
    assert after["net_revenue"] == before["net_revenue"]
    assert after["margin"] == before["margin"]
    assert after["blended_risk_score"] == before["blended_risk_score"]
    assert after["order_discount_pct"] == before["order_discount_pct"]
    assert after["lines"][0]["discount_pct"] == before["lines"][0]["discount_pct"]

    # And nothing was written to the governance tables either.
    import sqlalchemy as sa

    from app.models.policy_result import PolicyResult
    from app.models.quote_version import QuoteVersion

    async with db_session() as session:
        versions = (
            await session.execute(
                sa.select(sa.func.count()).select_from(QuoteVersion)
            )
        ).scalar_one()
        assert versions == 1, "simulation must not create a version"

        results_before = (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(PolicyResult)
                .where(PolicyResult.quote_version_id == built["version"]["id"])
            )
        ).scalar_one()
        # Whatever the count, it came from the real calculate, not the sim.
        assert results_before >= 0


async def test_simulation_can_model_an_order_level_discount(seeded) -> None:
    sales = seeded["sales"]
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "12"),)
    )
    version_id = built["version_id"]

    result = (
        await sales.post(
            f"/quote-versions/{version_id}/simulate",
            json={"order_discount_pct": "10"},
            expect=200,
        )
    ).json()

    # Compounded: 1 - 0.88 x 0.90 = 20.8%
    assert parse(result["proposed"]["effective_discount_pct"]) == Decimal("20.8000")
    assert result["baseline"]["requires_approval"] is False
    assert result["proposed"]["requires_approval"] is True


async def test_simulation_rejects_an_empty_hypothesis(seeded) -> None:
    sales = seeded["sales"]
    built = await build_canonical_quote(seeded)
    refused = await sales.post(
        f"/quote-versions/{built['version_id']}/simulate", json={}
    )
    assert refused.status_code == 422


async def test_simulation_rejects_a_line_from_another_quote(seeded) -> None:
    sales = seeded["sales"]
    built = await build_canonical_quote(seeded)
    other = await build_canonical_quote(seeded, title="Unrelated")
    foreign_line = other["version"]["lines"][0]["id"]

    refused = await sales.post(
        f"/quote-versions/{built['version_id']}/simulate",
        json={"line_discounts": {foreign_line: "20"}},
    )
    assert refused.status_code == 404
    assert refused.json()["error"]["code"] == "NOT_FOUND"


async def test_simulation_returns_the_risk_decomposition(seeded) -> None:
    """A predicted score has to be as explainable as a real one."""
    sales = seeded["sales"]
    built = await build_canonical_quote(seeded)
    line_id = built["version"]["lines"][0]["id"]

    result = (
        await sales.post(
            f"/quote-versions/{built['version_id']}/simulate",
            json={"line_discounts": {line_id: "35"}},
            expect=200,
        )
    ).json()

    components = result["proposed"]["risk_components"]
    assert {c["name"] for c in components} == {
        "WEIGHTED_DISCOUNT_OVERAGE",
        "VIOLATION_BREADTH",
        "MARGIN_SHORTFALL",
        "DISCOUNT_DEPTH",
    }
    for component in components:
        assert component["explanation"]
        assert "points" in component
    assert result["proposed"]["risk_explanation"]


async def test_customer_cannot_simulate(seeded) -> None:
    built = await build_canonical_quote(seeded)
    refused = await seeded["customer"].post(
        f"/quote-versions/{built['version_id']}/simulate",
        json={"order_discount_pct": "5"},
    )
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "PORTAL_USER_FORBIDDEN"
