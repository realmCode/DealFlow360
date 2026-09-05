"""PolicyEngine: per-line ceilings, margin floor, blended risk, explainability."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.config import settings
from app.enums import (
    ApprovalLevel,
    CustomerTier,
    PolicyResultStatus,
    ProductCategory,
    RiskBand,
)
from app.services.policy_engine import (
    CAP_BREADTH,
    CAP_DEPTH,
    CAP_MARGIN,
    CAP_OVERAGE,
    TIER_SENSITIVITY,
    PolicyEngine,
)
from tests.conftest import build_canonical_quote, money as parse


def _results(payload: dict, rule: str) -> list[dict]:
    return [r for r in payload["policy_results"] if r["rule"] == rule]


def _violations(payload: dict) -> list[dict]:
    return [r for r in payload["policy_results"] if r["status"] == "VIOLATED"]


# ------------------------------------------------- per-line category ceilings
async def test_discount_within_ceiling_passes(seeded) -> None:
    """Gold hardware ceiling is 15%; 10% passes with headroom."""
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "10"),)
    )
    sales = seeded["sales"]
    payload = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()

    ceiling = _results(payload, "CATEGORY_DISCOUNT_CEILING")[0]
    assert ceiling["status"] == "PASSED"
    assert parse(ceiling["actual_value"]) == Decimal("10.0000")
    assert parse(ceiling["threshold_value"]) == Decimal("15.0000")
    assert "within" in ceiling["reason"]
    assert "5 percentage points of headroom" in ceiling["reason"]
    assert payload["requires_approval"] is False
    assert payload["required_approvals"] == []


async def test_discount_near_ceiling_is_a_warning_not_a_pass(seeded) -> None:
    """14% of a 15% ceiling is 93% of the limit — flagged, but not violated."""
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "14"),)
    )
    sales = seeded["sales"]
    payload = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()
    ceiling = _results(payload, "CATEGORY_DISCOUNT_CEILING")[0]
    assert ceiling["status"] == "WARNING"
    assert "only 1 percentage points of headroom remain" in ceiling["reason"]
    # A warning must not require approval — it is information, not a breach.
    assert payload["requires_approval"] is False


async def test_discount_above_ceiling_requires_manager_approval(seeded) -> None:
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "18"),)
    )
    sales = seeded["sales"]
    payload = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()

    ceiling = _results(payload, "CATEGORY_DISCOUNT_CEILING")[0]
    assert ceiling["status"] == "VIOLATED"
    assert parse(ceiling["overage_points"]) == Decimal("3.0000")
    assert ceiling["required_action"] == "SALES_MANAGER"
    assert (
        "exceeds the Gold tier ceiling of 15% by 3 percentage points"
        in ceiling["reason"]
    )
    assert payload["requires_approval"] is True
    assert [r["type"] for r in payload["required_approvals"]] == ["SALES_MANAGER"]


async def test_service_ceiling_is_stricter_than_hardware_ceiling(seeded) -> None:
    """The same 12% discount passes on hardware and breaches on service.

    This is the case a single global threshold gets wrong.
    """
    built = await build_canonical_quote(
        seeded,
        lines=(("HW-LAPTOP-01", "10", "12"), ("SV-INSTALL-01", "1", "12")),
    )
    sales = seeded["sales"]
    payload = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()

    by_category = {
        r["scope_category"]: r for r in _results(payload, "CATEGORY_DISCOUNT_CEILING")
    }
    assert by_category["HARDWARE"]["status"] == "PASSED"
    assert parse(by_category["HARDWARE"]["threshold_value"]) == Decimal("15.0000")
    assert by_category["SERVICE"]["status"] == "VIOLATED"
    assert parse(by_category["SERVICE"]["threshold_value"]) == Decimal("10.0000")
    assert parse(by_category["SERVICE"]["overage_points"]) == Decimal("2.0000")


async def test_each_line_is_evaluated_against_its_own_policy(seeded) -> None:
    """The spec case: 12% laptop (ok) + 18% service (8 points over)."""
    built = await build_canonical_quote(
        seeded,
        lines=(("HW-LAPTOP-01", "100", "12"), ("SV-INSTALL-01", "1", "18")),
    )
    sales = seeded["sales"]
    payload = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()

    service = next(
        r
        for r in _results(payload, "CATEGORY_DISCOUNT_CEILING")
        if r["scope_category"] == "SERVICE"
    )
    assert service["status"] == "VIOLATED"
    assert parse(service["actual_value"]) == Decimal("18.0000")
    assert parse(service["threshold_value"]) == Decimal("10.0000")
    assert parse(service["overage_points"]) == Decimal("8.0000")
    assert service["scope_tier"] == "GOLD"
    assert service["required_action"] == "SALES_MANAGER"

    hardware = next(
        r
        for r in _results(payload, "CATEGORY_DISCOUNT_CEILING")
        if r["scope_category"] == "HARDWARE"
    )
    assert hardware["status"] == "PASSED"


async def test_fallback_policy_applies_when_no_tier_rule_exists(seeded) -> None:
    """A SILVER customer falls through to the 10% standard hardware ceiling."""
    sales = seeded["sales"]
    customer = (
        await sales.post(
            "/customers",
            json={
                "customer_organization_name": "Globex Industries",
                "display_name": "Globex Industries",
                "tier": "SILVER",
                "payment_terms": "NET_30",
            },
            expect=201,
        )
    ).json()
    deal = (
        await sales.post(
            "/deals",
            json={"name": "Globex", "customer_profile_id": customer["id"]},
            expect=201,
        )
    ).json()
    quote = (
        await sales.post(
            f"/deals/{deal['id']}/quotes",
            json={
                "title": "Globex",
                "lines": [
                    {
                        "product_id": seeded["products"]["HW-LAPTOP-01"],
                        "quantity": "5",
                        "discount_pct": "12",
                    }
                ],
            },
            expect=201,
        )
    ).json()
    payload = (
        await sales.get(
            f"/quote-versions/{quote['current_version_id']}/policy-results",
            expect=200,
        )
    ).json()
    ceiling = _results(payload, "CATEGORY_DISCOUNT_CEILING")[0]
    assert ceiling["status"] == "VIOLATED"
    assert parse(ceiling["threshold_value"]) == Decimal("10.0000")
    assert ceiling["detail"]["policy_code"] == "STD-HW-CEILING"


async def test_uncovered_category_is_reported_not_silently_ignored(seeded) -> None:
    """No SOFTWARE ceiling exists — the engine says so instead of passing."""
    admin = seeded["admin"]
    sales = seeded["sales"]
    product = (
        await admin.post(
            "/admin/products",
            json={
                "sku": "SW-CRM-01",
                "name": "CRM Licence",
                "category": "SOFTWARE",
                "list_price": "900.0000",
                "internal_cost": "100.0000",
            },
            expect=201,
        )
    ).json()
    deal = (
        await sales.post(
            "/deals",
            json={
                "name": "Software deal",
                "customer_profile_id": seeded["customer_profile_id"],
            },
            expect=201,
        )
    ).json()
    quote = (
        await sales.post(
            f"/deals/{deal['id']}/quotes",
            json={
                "title": "Software",
                "lines": [
                    {"product_id": product["id"], "quantity": "1", "discount_pct": "40"}
                ],
            },
            expect=201,
        )
    ).json()
    payload = (
        await sales.get(
            f"/quote-versions/{quote['current_version_id']}/policy-results",
            expect=200,
        )
    ).json()
    ceiling = _results(payload, "CATEGORY_DISCOUNT_CEILING")[0]
    assert ceiling["status"] == "NOT_APPLICABLE"
    assert "No discount ceiling is configured" in ceiling["reason"]


# ---------------------------------------------------------------- min margin
async def test_margin_within_floor_passes(seeded) -> None:
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "10"),)
    )
    sales = seeded["sales"]
    payload = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()
    margin = _results(payload, "MIN_MARGIN")[0]
    assert margin["status"] == "PASSED"
    assert "clears the 10% minimum" in margin["reason"]


async def test_margin_violation_requires_finance_and_explains_the_gap(
    seeded,
) -> None:
    """A 40% laptop discount drops margin to 11.1%... push to 45% to breach."""
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "45"),)
    )
    sales = seeded["sales"]
    version = (
        await sales.get(f"/quote-versions/{built['version_id']}", expect=200)
    ).json()
    # 1200 * 0.55 = 660/unit vs 800 cost -> negative margin.
    assert parse(version["margin_pct"]) < Decimal("0")

    payload = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()
    margin = _results(payload, "MIN_MARGIN")[0]
    assert margin["status"] == "VIOLATED"
    assert margin["required_action"] == "FINANCE"
    assert "below the required minimum of 10%" in margin["reason"]
    assert parse(margin["threshold_value"]) == Decimal("10.0000")
    assert parse(margin["overage_points"]) > Decimal("0")
    assert "FINANCE" in [r["type"] for r in payload["required_approvals"]]


# ------------------------------------------------- discount signing authority
async def test_discount_authority_routes_to_finance_on_amount_not_margin(
    seeded,
) -> None:
    """The canonical demo: healthy 24% margin, but 28,090 of discount given.

    Margin passes, yet Finance is required because the give-away exceeds a
    Sales Manager's 20,000 signing authority. Routing must be driven by that
    policy row, not by a hardcoded demo rule.
    """
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    payload = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()

    margin = _results(payload, "MIN_MARGIN")[0]
    assert margin["status"] == "PASSED"

    authority = _results(payload, "DISCOUNT_AMOUNT_AUTHORITY")[0]
    assert authority["status"] == "VIOLATED"
    assert authority["unit"] == "AMOUNT"
    assert parse(authority["actual_value"]) == Decimal("28090.0000")
    assert parse(authority["threshold_value"]) == Decimal("20000.0000")
    assert authority["required_action"] == "FINANCE"
    assert "signing authority limit" in authority["reason"]
    # Amount-unit rules must not pollute a percentage-point risk score.
    assert parse(authority["risk_contribution"]) == Decimal("0.0000")

    levels = [r["type"] for r in payload["required_approvals"]]
    assert levels == ["SALES_MANAGER", "FINANCE"], "escalation order must hold"


async def test_discount_authority_passes_below_the_limit(seeded) -> None:
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "18"),)
    )
    sales = seeded["sales"]
    payload = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()
    authority = _results(payload, "DISCOUNT_AMOUNT_AUTHORITY")[0]
    assert authority["status"] == "PASSED"
    assert [r["type"] for r in payload["required_approvals"]] == ["SALES_MANAGER"]


# ------------------------------------------------------------- blended risk
async def test_blended_risk_is_zero_when_nothing_is_breached(seeded) -> None:
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "5"),)
    )
    sales = seeded["sales"]
    payload = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()
    risk = payload["blended_risk"]
    # A 5% discount still contributes depth points, so the score is > 0 but
    # the band stays LOW and no approval is required.
    assert risk["band"] in ("NONE", "LOW")
    assert payload["requires_approval"] is False


async def test_blended_risk_matches_the_documented_formula(seeded) -> None:
    """Recompute the canonical quote's score by hand from the README formula.

    Lines (net revenue 132,710):
      laptops     98,400 net, 18% vs 15% -> 3 pts over, share 0.741391...
      monitors    33,600 net, 16% vs 15% -> 1 pt  over, share 0.253184...
      install        410 net, 18% vs 10% -> 8 pts over, share 0.003089...
      support        300 net,  0% vs 10% -> pass
    """
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    payload = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()
    risk = payload["blended_risk"]
    components = {c["name"]: c for c in risk["components"]}

    net = Decimal("132710")
    weighted = (
        Decimal("3") * (Decimal("98400") / net)
        + Decimal("1") * (Decimal("33600") / net)
        + Decimal("8") * (Decimal("410") / net)
    )
    expected_overage = min(
        CAP_OVERAGE,
        (weighted * settings.risk_discount_overage_weight).quantize(
            Decimal("0.0001")
        ),
    )
    assert parse(components["WEIGHTED_DISCOUNT_OVERAGE"]["points"]) == expected_overage

    expected_breadth = min(CAP_BREADTH, Decimal("3") * settings.risk_breadth_weight)
    assert parse(components["VIOLATION_BREADTH"]["points"]) == expected_breadth

    assert parse(components["MARGIN_SHORTFALL"]["points"]) == Decimal("0.0000")

    effective = Decimal("17.4689")  # 28,090 / 160,800
    expected_depth = min(
        CAP_DEPTH,
        (effective * settings.risk_depth_weight).quantize(Decimal("0.0001")),
    )
    assert parse(components["DISCOUNT_DEPTH"]["points"]) == expected_depth

    raw = expected_overage + expected_breadth + expected_depth
    expected_score = min(
        Decimal("100"),
        (raw * TIER_SENSITIVITY[CustomerTier.GOLD]).quantize(Decimal("0.0001")),
    )
    assert parse(risk["score"]) == expected_score
    assert parse(risk["tier_sensitivity"]) == TIER_SENSITIVITY[CustomerTier.GOLD]
    assert risk["tier"] == "GOLD"


async def test_blended_risk_is_deterministic_across_repeated_evaluations(
    seeded,
) -> None:
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    scores = set()
    for _ in range(4):
        payload = (
            await sales.get(
                f"/quote-versions/{built['version_id']}/policy-results", expect=200
            )
        ).json()
        scores.add(payload["blended_risk"]["score"])
    assert len(scores) == 1, f"score is not deterministic: {scores}"


async def test_breadth_component_rises_with_more_violating_lines(seeded) -> None:
    """Several lines each slightly over must move the combined exposure."""
    sales = seeded["sales"]

    one = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "10", "16"),), title="one breach"
    )
    three = await build_canonical_quote(
        seeded,
        lines=(
            ("HW-LAPTOP-01", "10", "16"),
            ("HW-MONITOR-27", "10", "16"),
            ("SV-INSTALL-01", "1", "11"),
        ),
        title="three breaches",
    )

    def breadth(payload: dict) -> Decimal:
        return parse(
            next(
                c
                for c in payload["blended_risk"]["components"]
                if c["name"] == "VIOLATION_BREADTH"
            )["points"]
        )

    p1 = (
        await sales.get(
            f"/quote-versions/{one['version_id']}/policy-results", expect=200
        )
    ).json()
    p3 = (
        await sales.get(
            f"/quote-versions/{three['version_id']}/policy-results", expect=200
        )
    ).json()

    assert breadth(p3) > breadth(p1)
    assert parse(p3["blended_risk"]["score"]) > parse(p1["blended_risk"]["score"])


async def test_revenue_weighting_stops_a_tiny_line_dominating(seeded) -> None:
    """8 points over on a $410 line must matter less than 3 points on $98,400."""
    sales = seeded["sales"]
    tiny = await build_canonical_quote(
        seeded,
        lines=(("HW-LAPTOP-01", "100", "0"), ("SV-INSTALL-01", "1", "18")),
        title="tiny breach",
    )
    big = await build_canonical_quote(
        seeded,
        lines=(("HW-LAPTOP-01", "100", "18"), ("SV-INSTALL-01", "1", "0")),
        title="big breach",
    )

    p_tiny = (
        await sales.get(
            f"/quote-versions/{tiny['version_id']}/policy-results", expect=200
        )
    ).json()
    p_big = (
        await sales.get(
            f"/quote-versions/{big['version_id']}/policy-results", expect=200
        )
    ).json()

    def component(payload: dict) -> Decimal:
        return parse(
            next(
                c
                for c in payload["blended_risk"]["components"]
                if c["name"] == "WEIGHTED_DISCOUNT_OVERAGE"
            )["points"]
        )

    assert component(p_big) > component(p_tiny)


async def test_risk_components_are_individually_capped(seeded) -> None:
    """A catastrophic discount must not produce an unbounded score."""
    built = await build_canonical_quote(
        seeded,
        lines=(
            ("HW-LAPTOP-01", "100", "95"),
            ("HW-MONITOR-27", "100", "95"),
            ("SV-INSTALL-01", "1", "95"),
            ("SB-SUPPORT-01", "1", "95"),
        ),
    )
    sales = seeded["sales"]
    payload = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()
    risk = payload["blended_risk"]
    assert parse(risk["score"]) <= Decimal("100")
    assert risk["band"] == "CRITICAL"
    for component in risk["components"]:
        assert parse(component["points"]) <= parse(component["cap"])


async def test_high_risk_escalates_to_finance_even_without_a_finance_policy(
    seeded,
) -> None:
    """The documented escalation rule: score >= threshold pulls in Finance."""
    built = await build_canonical_quote(
        seeded, lines=(("HW-LAPTOP-01", "100", "90"),)
    )
    sales = seeded["sales"]
    payload = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()
    assert parse(payload["blended_risk"]["score"]) >= (
        settings.risk_finance_escalation_threshold
    )
    finance = next(
        r for r in payload["required_approvals"] if r["type"] == "FINANCE"
    )
    assert any(
        "finance escalation threshold" in reason for reason in finance["triggered_by"]
    )


async def test_explainability_is_present_on_every_result(seeded) -> None:
    """No bare numbers: every result carries prose and the numbers behind it."""
    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    payload = (
        await sales.get(
            f"/quote-versions/{built['version_id']}/policy-results", expect=200
        )
    ).json()

    assert payload["policy_results"], "expected at least one evaluated policy"
    for result in payload["policy_results"]:
        assert result["reason"], f"{result['rule']} has no reason"
        assert len(result["reason"]) > 25, "reason must be a sentence, not a code"
        assert result["status"] in {
            "PASSED",
            "WARNING",
            "VIOLATED",
            "NOT_APPLICABLE",
        }
        assert "actual_value" in result and "threshold_value" in result

    risk = payload["blended_risk"]
    assert risk["formula"].startswith("score = min(100")
    assert risk["explanation"]
    assert len(risk["components"]) == 4
    for component in risk["components"]:
        assert component["explanation"]
        assert "weight" in component and "cap" in component


def test_tier_sensitivity_is_ordered_and_covers_every_tier() -> None:
    assert set(TIER_SENSITIVITY) == set(CustomerTier)
    assert (
        TIER_SENSITIVITY[CustomerTier.PLATINUM]
        > TIER_SENSITIVITY[CustomerTier.GOLD]
        > TIER_SENSITIVITY[CustomerTier.SILVER]
        > TIER_SENSITIVITY[CustomerTier.BRONZE]
    )


def test_component_caps_sum_above_one_hundred_so_the_clamp_is_real() -> None:
    assert CAP_OVERAGE + CAP_BREADTH + CAP_MARGIN + CAP_DEPTH == Decimal("115")


async def test_policy_results_are_replaced_not_appended(seeded) -> None:
    """Re-evaluating must not accumulate stale rows."""
    from tests.conftest import db_session
    import uuid

    from sqlalchemy import func, select

    from app.models.policy_result import PolicyResult

    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    version_id = uuid.UUID(built["version_id"])

    async def count() -> int:
        async with db_session() as s:
            return int(
                (
                    await s.execute(
                        select(func.count())
                        .select_from(PolicyResult)
                        .where(PolicyResult.quote_version_id == version_id)
                    )
                ).scalar_one()
            )

    first = await count()
    await sales.post(f"/quote-versions/{built['version_id']}/calculate", expect=200)
    await sales.post(f"/quote-versions/{built['version_id']}/calculate", expect=200)
    assert await count() == first


@pytest.mark.parametrize(
    ("score", "band"),
    [
        ("0", RiskBand.NONE),
        ("0.5", RiskBand.LOW),
        ("14.9999", RiskBand.LOW),
        ("15", RiskBand.MEDIUM),
        ("39.9999", RiskBand.MEDIUM),
        ("40", RiskBand.HIGH),
        ("69.9999", RiskBand.HIGH),
        ("70", RiskBand.CRITICAL),
        ("100", RiskBand.CRITICAL),
    ],
)
def test_risk_bands_are_contiguous(score: str, band: RiskBand) -> None:
    from app.services.policy_engine import _band_for

    assert _band_for(Decimal(score)) is band


def test_policy_matching_prefers_the_most_specific_rule() -> None:
    """A Gold+Hardware rule must beat a global hardware rule."""
    from types import SimpleNamespace

    from app.enums import PolicyType

    generic = SimpleNamespace(
        policy_type=PolicyType.CATEGORY_DISCOUNT_CEILING,
        customer_tier=None,
        product_category=ProductCategory.HARDWARE,
        customer_profile_id=None,
        specificity=1,
        priority=10,
        code="GENERIC",
        threshold_value=Decimal("10"),
        required_action=ApprovalLevel.SALES_MANAGER,
    )
    specific = SimpleNamespace(
        policy_type=PolicyType.CATEGORY_DISCOUNT_CEILING,
        customer_tier=CustomerTier.GOLD,
        product_category=ProductCategory.HARDWARE,
        customer_profile_id=None,
        specificity=3,
        priority=900,  # worse priority but far more specific
        code="GOLD",
        threshold_value=Decimal("15"),
        required_action=ApprovalLevel.SALES_MANAGER,
    )
    chosen = PolicyEngine._match(
        [generic, specific],
        PolicyType.CATEGORY_DISCOUNT_CEILING,
        tier=CustomerTier.GOLD,
        category=ProductCategory.HARDWARE,
    )
    assert chosen is specific


def test_policy_result_status_enum_is_exhaustive() -> None:
    assert {s.value for s in PolicyResultStatus} == {
        "PASSED",
        "WARNING",
        "VIOLATED",
        "NOT_APPLICABLE",
    }
