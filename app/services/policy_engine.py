"""PolicyEngine — governance evaluation with mandatory explainability.

Two hard rules:

1. **No bare scores.** Every result carries ``reason`` prose plus the actual
   value, the threshold, the overage and the required action.
2. **No hardcoded routing.** Which approvals a quote needs is derived from the
   ``required_action`` of the policy rows that actually fire, plus one
   documented risk-escalation rule. Nothing is special-cased for the demo.

================================================================
BLENDED RISK ALGORITHM  (deterministic, testable, unit-consistent)
================================================================

Four additive components, each individually capped, then scaled by a
customer-tier sensitivity factor and clamped to 0-100.

  C1 — WEIGHTED DISCOUNT OVERAGE                        cap 45
        For every line L that breaches its category ceiling:
            overage_L       = discount_pct_L - ceiling_L      (pct points)
            revenue_share_L = net_amount_L / net_revenue       (0..1)
            weighted_L      = overage_L x revenue_share_L
        raw1    = SUM(weighted_L)
        points1 = min(45, raw1 x W_OVERAGE)          W_OVERAGE = 3.0
        -> Revenue-weighting is what stops an 8-point breach on a $410
           service line from dominating a 3-point breach on $98,400 of
           hardware. Exposure, not indignation.

  C2 — BREADTH OF VIOLATION                             cap 15
        raw2    = count of lines breaching a ceiling
        points2 = min(15, raw2 x W_BREADTH)          W_BREADTH = 5.0
        -> Several lines each slightly over their threshold is a pattern of
           erosion, not a rounding error; combined exposure must move the
           score even when each individual overage is small.

  C3 — MARGIN SHORTFALL                                 cap 40
        raw3    = max(0, margin_floor_pct - actual_margin_pct)
        points3 = min(40, raw3 x W_MARGIN)           W_MARGIN = 5.0

  C4 — CUMULATIVE DISCOUNT DEPTH                        cap 15
        raw4    = total_discount / gross_revenue x 100
        points4 = min(15, raw4 x W_DEPTH)            W_DEPTH = 0.4
        -> Total giveaway matters even when every line is inside its ceiling.

  TIER SENSITIVITY
        raw_total = points1 + points2 + points3 + points4     (0..115)
        score     = min(100, raw_total x S_tier)
        S_tier: PLATINUM 1.20 | GOLD 1.10 | SILVER 1.00 | BRONZE 0.95
        -> Senior tiers already receive the most generous ceilings, so
           breaching one is a larger deviation from an already-concessive
           baseline, and those accounts concentrate more revenue.

  BANDS
        score == 0        -> NONE
        0  < score < 15   -> LOW
        15 <= score < 40  -> MEDIUM
        40 <= score < 70  -> HIGH
        70 <= score       -> CRITICAL

APPROVAL ROUTING
        required = { policy.required_action : policy VIOLATED }
        plus FINANCE when score >= RISK_FINANCE_ESCALATION_THRESHOLD (60)
        Steps are created in escalation order (SALES_MANAGER then FINANCE);
        the highest required level is the final authority.

Amount-threshold policies (``DISCOUNT_AMOUNT_AUTHORITY``) deliberately
contribute **0** to the score: signing authority is a question of *who* must
approve, not *how risky* the deal is, and mixing currency into a
percentage-point score would make the number meaningless. They still route
approvals.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.enums import (
    APPROVAL_LEVEL_ORDER,
    ApprovalLevel,
    CustomerTier,
    PolicyComparison,
    PolicyResultStatus,
    PolicyType,
    PolicyUnit,
    ProductCategory,
    RiskBand,
    Severity,
)
from app.models.customer_profile import CustomerProfile
from app.models.policy import Policy
from app.models.policy_result import PolicyResult
from app.models.quote_line import QuoteLine
from app.models.quote_version import QuoteVersion
from app.services.commercial_engine import HUNDRED, ZERO, money, pct

# Component caps (percentage points of the 0-100 score).
CAP_OVERAGE = Decimal("45")
CAP_BREADTH = Decimal("15")
CAP_MARGIN = Decimal("40")
CAP_DEPTH = Decimal("15")

TIER_SENSITIVITY: dict[CustomerTier, Decimal] = {
    CustomerTier.PLATINUM: Decimal("1.20"),
    CustomerTier.GOLD: Decimal("1.10"),
    CustomerTier.SILVER: Decimal("1.00"),
    CustomerTier.BRONZE: Decimal("0.95"),
}

#: A discount this close to its ceiling is reported as WARNING, not PASSED.
WARNING_BAND_RATIO = Decimal("0.90")

FORMULA = (
    "score = min(100, ("
    "min(45, S(overage_pts x revenue_share) x 3.0) + "
    "min(15, violating_line_count x 5.0) + "
    "min(40, margin_shortfall_pts x 5.0) + "
    "min(15, effective_discount_pct x 0.4)"
    ") x tier_sensitivity)"
)


@dataclass(slots=True)
class PolicyOutcome:
    """One explainable evaluation. Maps 1:1 onto a ``policy_results`` row."""

    rule: str
    status: PolicyResultStatus
    reason: str
    actual_value: Decimal = ZERO
    threshold_value: Decimal = ZERO
    overage_points: Decimal = ZERO
    unit: PolicyUnit = PolicyUnit.PERCENT
    severity: Severity = Severity.LOW
    subject: str | None = None
    required_action: ApprovalLevel | None = None
    scope_category: ProductCategory | None = None
    scope_tier: CustomerTier | None = None
    policy_id: uuid.UUID | None = None
    quote_line_id: uuid.UUID | None = None
    risk_contribution: Decimal = ZERO
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def violated(self) -> bool:
        return self.status is PolicyResultStatus.VIOLATED

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "status": self.status.value,
            "subject": self.subject,
            "category": self.scope_category.value if self.scope_category else None,
            "tier": self.scope_tier.value if self.scope_tier else None,
            "actual": str(self.actual_value),
            "threshold": str(self.threshold_value),
            "overage_points": str(self.overage_points),
            "unit": self.unit.value,
            "severity": self.severity.value,
            "reason": self.reason,
            "required_action": (
                self.required_action.value if self.required_action else None
            ),
            "risk_contribution": str(self.risk_contribution),
        }


@dataclass(slots=True)
class RiskComponentResult:
    name: str
    raw_value: Decimal
    weight: Decimal
    points: Decimal
    cap: Decimal
    explanation: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "raw_value": str(self.raw_value),
            "weight": str(self.weight),
            "points": str(self.points),
            "cap": str(self.cap),
            "explanation": self.explanation,
        }


@dataclass(slots=True)
class BlendedRisk:
    score: Decimal
    band: RiskBand
    tier: CustomerTier
    tier_sensitivity: Decimal
    components: list[RiskComponentResult]
    formula: str
    explanation: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": str(self.score),
            "band": self.band.value,
            "tier": self.tier.value,
            "tier_sensitivity": str(self.tier_sensitivity),
            "components": [c.as_dict() for c in self.components],
            "formula": self.formula,
            "explanation": self.explanation,
        }


@dataclass(slots=True)
class RequiredApprovalSpec:
    level: ApprovalLevel
    reason: str
    triggered_by: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.level.value,
            "reason": self.reason,
            "triggered_by": list(self.triggered_by),
        }


@dataclass(slots=True)
class PolicyEvaluation:
    quote_version_id: uuid.UUID
    outcomes: list[PolicyOutcome]
    blended_risk: BlendedRisk
    required_approvals: list[RequiredApprovalSpec]
    evaluated_at: datetime

    @property
    def violations(self) -> list[PolicyOutcome]:
        return [o for o in self.outcomes if o.violated]

    @property
    def requires_approval(self) -> bool:
        return bool(self.required_approvals)

    @property
    def highest_level(self) -> ApprovalLevel | None:
        if not self.required_approvals:
            return None
        return max(self.required_approvals, key=lambda r: APPROVAL_LEVEL_ORDER[r.level]).level

    def summary(self) -> dict[str, Any]:
        return {
            "violation_count": len(self.violations),
            "blended_risk": self.blended_risk.as_dict(),
            "required_approvals": [r.as_dict() for r in self.required_approvals],
            "violations": [o.as_dict() for o in self.violations],
        }


class PolicyEngine:
    # ------------------------------------------------------------ policy load
    @staticmethod
    async def active_policies(
        session: AsyncSession,
        organization_id: uuid.UUID,
        *,
        on_date: date | None = None,
    ) -> list[Policy]:
        today = on_date or datetime.now(UTC).date()
        result = await session.execute(
            select(Policy).where(
                Policy.organization_id == organization_id,
                Policy.is_active.is_(True),
            )
        )
        policies = list(result.scalars())
        return [
            p
            for p in policies
            if (p.effective_from is None or p.effective_from <= today)
            and (p.effective_to is None or p.effective_to >= today)
        ]

    @staticmethod
    def _match(
        policies: Sequence[Policy],
        policy_type: PolicyType,
        *,
        tier: CustomerTier | None = None,
        category: ProductCategory | None = None,
        customer_profile_id: uuid.UUID | None = None,
    ) -> Policy | None:
        """Most specific match wins; ``priority`` breaks ties within a scope."""
        candidates = [
            p
            for p in policies
            if p.policy_type is policy_type
            and (p.customer_tier is None or p.customer_tier == tier)
            and (p.product_category is None or p.product_category == category)
            and (
                p.customer_profile_id is None
                or p.customer_profile_id == customer_profile_id
            )
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda p: (-p.specificity, p.priority, p.code))

    # -------------------------------------------------------------- evaluate
    @classmethod
    def evaluate(
        cls,
        *,
        version: QuoteVersion,
        lines: Sequence[QuoteLine],
        profile: CustomerProfile | None,
        policies: Sequence[Policy],
    ) -> PolicyEvaluation:
        """Pure evaluation — no I/O, so it is trivially unit-testable."""
        tier = profile.tier if profile else CustomerTier.BRONZE
        profile_id = profile.id if profile else None
        outcomes: list[PolicyOutcome] = []

        net_revenue = Decimal(version.net_revenue or ZERO)

        # ------------------------------------- C1 + C2: per-line ceilings
        weighted_overage_total = ZERO
        violating_lines = 0

        for line in lines:
            policy = cls._match(
                policies,
                PolicyType.CATEGORY_DISCOUNT_CEILING,
                tier=tier,
                category=line.category,
                customer_profile_id=profile_id,
            )
            if policy is None:
                outcomes.append(
                    PolicyOutcome(
                        rule="CATEGORY_DISCOUNT_CEILING",
                        status=PolicyResultStatus.NOT_APPLICABLE,
                        subject=line.description,
                        actual_value=pct(line.discount_pct),
                        scope_category=line.category,
                        scope_tier=tier,
                        quote_line_id=line.id,
                        reason=(
                            f"No discount ceiling is configured for "
                            f"{line.category.value.title()} products at "
                            f"{tier.value.title()} tier, so the "
                            f"{pct(line.discount_pct)}% discount on "
                            f"'{line.description}' was not constrained."
                        ),
                        detail={"line_number": line.line_number},
                    )
                )
                continue

            actual = pct(line.discount_pct)
            threshold = pct(policy.threshold_value)
            revenue_share = (
                Decimal(line.net_amount) / net_revenue if net_revenue > ZERO else ZERO
            )

            if actual > threshold:
                overage = pct(actual - threshold)
                weighted = overage * revenue_share
                weighted_overage_total += weighted
                violating_lines += 1
                contribution = pct(
                    weighted * settings.risk_discount_overage_weight
                    + settings.risk_breadth_weight
                )
                outcomes.append(
                    PolicyOutcome(
                        rule="CATEGORY_DISCOUNT_CEILING",
                        status=PolicyResultStatus.VIOLATED,
                        subject=line.description,
                        actual_value=actual,
                        threshold_value=threshold,
                        overage_points=overage,
                        unit=PolicyUnit.PERCENT,
                        severity=policy.severity,
                        required_action=policy.required_action,
                        scope_category=line.category,
                        scope_tier=tier,
                        policy_id=policy.id,
                        quote_line_id=line.id,
                        risk_contribution=contribution,
                        reason=(
                            f"{line.category.value.title()} discount of "
                            f"{_trim(actual)}% on '{line.description}' exceeds the "
                            f"{tier.value.title()} tier ceiling of "
                            f"{_trim(threshold)}% by {_trim(overage)} percentage "
                            f"points."
                        ),
                        detail={
                            "policy_code": policy.code,
                            "line_number": line.line_number,
                            "line_net_amount": str(money(line.net_amount)),
                            "revenue_share": str(pct(revenue_share * HUNDRED)),
                            "weighted_overage": str(pct(weighted)),
                        },
                    )
                )
            else:
                near_limit = threshold > ZERO and actual >= threshold * WARNING_BAND_RATIO
                status = (
                    PolicyResultStatus.WARNING
                    if near_limit
                    else PolicyResultStatus.PASSED
                )
                headroom = pct(threshold - actual)
                reason = (
                    f"{line.category.value.title()} discount of {_trim(actual)}% on "
                    f"'{line.description}' is within the {tier.value.title()} tier "
                    f"ceiling of {_trim(threshold)}%"
                )
                reason += (
                    f", but only {_trim(headroom)} percentage points of headroom "
                    f"remain."
                    if near_limit
                    else f" with {_trim(headroom)} percentage points of headroom."
                )
                outcomes.append(
                    PolicyOutcome(
                        rule="CATEGORY_DISCOUNT_CEILING",
                        status=status,
                        subject=line.description,
                        actual_value=actual,
                        threshold_value=threshold,
                        overage_points=ZERO,
                        unit=PolicyUnit.PERCENT,
                        severity=Severity.LOW,
                        scope_category=line.category,
                        scope_tier=tier,
                        policy_id=policy.id,
                        quote_line_id=line.id,
                        reason=reason,
                        detail={
                            "policy_code": policy.code,
                            "line_number": line.line_number,
                            "headroom_points": str(headroom),
                        },
                    )
                )

        # ------------------------------------------------ C3: margin floor
        margin_policy = cls._match(
            policies,
            PolicyType.MIN_MARGIN,
            tier=tier,
            customer_profile_id=profile_id,
        )
        margin_shortfall = ZERO
        actual_margin = pct(version.margin_pct or ZERO)
        if margin_policy is not None:
            floor = pct(margin_policy.threshold_value)
            if actual_margin < floor:
                margin_shortfall = pct(floor - actual_margin)
                contribution = pct(
                    min(
                        CAP_MARGIN,
                        margin_shortfall * settings.risk_margin_weight,
                    )
                )
                outcomes.append(
                    PolicyOutcome(
                        rule="MIN_MARGIN",
                        status=PolicyResultStatus.VIOLATED,
                        subject="Quote margin",
                        actual_value=actual_margin,
                        threshold_value=floor,
                        overage_points=margin_shortfall,
                        unit=PolicyUnit.PERCENT,
                        severity=margin_policy.severity,
                        required_action=margin_policy.required_action,
                        scope_tier=tier,
                        policy_id=margin_policy.id,
                        risk_contribution=contribution,
                        reason=(
                            f"Margin is {_trim(margin_shortfall)}% below the required "
                            f"minimum of {_trim(floor)}% "
                            f"(actual {_trim(actual_margin)}%)."
                        ),
                        detail={
                            "policy_code": margin_policy.code,
                            "margin_amount": str(money(version.margin or ZERO)),
                            "net_revenue": str(money(net_revenue)),
                            "total_cost": str(money(version.total_cost or ZERO)),
                        },
                    )
                )
            else:
                outcomes.append(
                    PolicyOutcome(
                        rule="MIN_MARGIN",
                        status=PolicyResultStatus.PASSED,
                        subject="Quote margin",
                        actual_value=actual_margin,
                        threshold_value=floor,
                        unit=PolicyUnit.PERCENT,
                        severity=Severity.LOW,
                        scope_tier=tier,
                        policy_id=margin_policy.id,
                        reason=(
                            f"Margin of {_trim(actual_margin)}% clears the "
                            f"{_trim(floor)}% minimum by "
                            f"{_trim(pct(actual_margin - floor))} percentage points."
                        ),
                        detail={"policy_code": margin_policy.code},
                    )
                )

        # ------------------------------- discount authority (routing only)
        authority_policy = cls._match(
            policies,
            PolicyType.DISCOUNT_AMOUNT_AUTHORITY,
            tier=tier,
            customer_profile_id=profile_id,
        )
        if authority_policy is not None:
            given = money(version.total_discount or ZERO)
            limit = money(authority_policy.threshold_value)
            if given > limit:
                outcomes.append(
                    PolicyOutcome(
                        rule="DISCOUNT_AMOUNT_AUTHORITY",
                        status=PolicyResultStatus.VIOLATED,
                        subject="Total discount given",
                        actual_value=given,
                        threshold_value=limit,
                        overage_points=money(given - limit),
                        unit=PolicyUnit.AMOUNT,
                        severity=authority_policy.severity,
                        required_action=authority_policy.required_action,
                        scope_tier=tier,
                        policy_id=authority_policy.id,
                        risk_contribution=ZERO,
                        reason=(
                            f"Total discount of {version.currency} {given} exceeds the "
                            f"{_level_label(authority_policy.required_action)} signing "
                            f"authority limit of {version.currency} {limit} by "
                            f"{version.currency} {money(given - limit)}."
                        ),
                        detail={
                            "policy_code": authority_policy.code,
                            "note": (
                                "Signing-authority rules govern who must approve, not "
                                "how risky the deal is, so this rule contributes 0 to "
                                "the blended risk score."
                            ),
                        },
                    )
                )
            else:
                outcomes.append(
                    PolicyOutcome(
                        rule="DISCOUNT_AMOUNT_AUTHORITY",
                        status=PolicyResultStatus.PASSED,
                        subject="Total discount given",
                        actual_value=given,
                        threshold_value=limit,
                        unit=PolicyUnit.AMOUNT,
                        scope_tier=tier,
                        policy_id=authority_policy.id,
                        reason=(
                            f"Total discount of {version.currency} {given} is within "
                            f"the {version.currency} {limit} signing authority limit."
                        ),
                        detail={"policy_code": authority_policy.code},
                    )
                )

        # ------------------------------------------- payment terms (optional)
        terms_policy = cls._match(
            policies,
            PolicyType.PAYMENT_TERMS_LIMIT,
            tier=tier,
            customer_profile_id=profile_id,
        )
        if terms_policy is not None:
            days = Decimal(_terms_days(version))
            limit_days = Decimal(terms_policy.threshold_value)
            violated = (
                days > limit_days
                if terms_policy.comparison is PolicyComparison.LTE
                else days < limit_days
            )
            outcomes.append(
                PolicyOutcome(
                    rule="PAYMENT_TERMS_LIMIT",
                    status=(
                        PolicyResultStatus.VIOLATED
                        if violated
                        else PolicyResultStatus.PASSED
                    ),
                    subject=version.payment_terms.value,
                    actual_value=days,
                    threshold_value=limit_days,
                    overage_points=max(ZERO, days - limit_days),
                    unit=PolicyUnit.DAYS,
                    severity=terms_policy.severity,
                    required_action=terms_policy.required_action if violated else None,
                    scope_tier=tier,
                    policy_id=terms_policy.id,
                    reason=(
                        f"Payment terms of {int(days)} days exceed the "
                        f"{int(limit_days)}-day limit for {tier.value.title()} tier."
                        if violated
                        else f"Payment terms of {int(days)} days are within the "
                        f"{int(limit_days)}-day limit."
                    ),
                    detail={"policy_code": terms_policy.code},
                )
            )

        blended = cls._blended_risk(
            tier=tier,
            weighted_overage_total=weighted_overage_total,
            violating_lines=violating_lines,
            margin_shortfall=margin_shortfall,
            effective_discount_pct=pct(version.effective_discount_pct or ZERO),
        )
        required = cls._route_approvals(outcomes, blended)

        return PolicyEvaluation(
            quote_version_id=version.id,
            outcomes=outcomes,
            blended_risk=blended,
            required_approvals=required,
            evaluated_at=datetime.now(UTC),
        )

    # ---------------------------------------------------------- risk scoring
    @staticmethod
    def _blended_risk(
        *,
        tier: CustomerTier,
        weighted_overage_total: Decimal,
        violating_lines: int,
        margin_shortfall: Decimal,
        effective_discount_pct: Decimal,
    ) -> BlendedRisk:
        w_overage = settings.risk_discount_overage_weight
        w_breadth = settings.risk_breadth_weight
        w_margin = settings.risk_margin_weight
        w_depth = settings.risk_depth_weight

        p1 = min(CAP_OVERAGE, pct(weighted_overage_total * w_overage))
        p2 = min(CAP_BREADTH, pct(Decimal(violating_lines) * w_breadth))
        p3 = min(CAP_MARGIN, pct(margin_shortfall * w_margin))
        p4 = min(CAP_DEPTH, pct(effective_discount_pct * w_depth))

        components = [
            RiskComponentResult(
                name="WEIGHTED_DISCOUNT_OVERAGE",
                raw_value=pct(weighted_overage_total),
                weight=w_overage,
                points=p1,
                cap=CAP_OVERAGE,
                explanation=(
                    f"Revenue-weighted ceiling overage of "
                    f"{_trim(pct(weighted_overage_total))} percentage points x weight "
                    f"{_trim(w_overage)} = {_trim(p1)} points (cap {_trim(CAP_OVERAGE)})."
                ),
            ),
            RiskComponentResult(
                name="VIOLATION_BREADTH",
                raw_value=Decimal(violating_lines),
                weight=w_breadth,
                points=p2,
                cap=CAP_BREADTH,
                explanation=(
                    f"{violating_lines} line(s) breach a ceiling x weight "
                    f"{_trim(w_breadth)} = {_trim(p2)} points (cap {_trim(CAP_BREADTH)})."
                ),
            ),
            RiskComponentResult(
                name="MARGIN_SHORTFALL",
                raw_value=pct(margin_shortfall),
                weight=w_margin,
                points=p3,
                cap=CAP_MARGIN,
                explanation=(
                    f"Margin shortfall of {_trim(pct(margin_shortfall))} percentage "
                    f"points x weight {_trim(w_margin)} = {_trim(p3)} points "
                    f"(cap {_trim(CAP_MARGIN)})."
                ),
            ),
            RiskComponentResult(
                name="DISCOUNT_DEPTH",
                raw_value=pct(effective_discount_pct),
                weight=w_depth,
                points=p4,
                cap=CAP_DEPTH,
                explanation=(
                    f"Effective discount of {_trim(pct(effective_discount_pct))}% x "
                    f"weight {_trim(w_depth)} = {_trim(p4)} points "
                    f"(cap {_trim(CAP_DEPTH)})."
                ),
            ),
        ]

        sensitivity = TIER_SENSITIVITY[tier]
        raw_total = p1 + p2 + p3 + p4
        score = min(Decimal("100"), pct(raw_total * sensitivity))
        band = _band_for(score)

        if score == ZERO:
            explanation = (
                "No governance thresholds were breached: the blended risk score is 0."
            )
        else:
            explanation = (
                f"Blended risk {_trim(score)}/100 ({band.value}) = "
                f"({_trim(p1)} overage + {_trim(p2)} breadth + {_trim(p3)} margin + "
                f"{_trim(p4)} depth) x {_trim(sensitivity)} {tier.value.title()} tier "
                f"sensitivity."
            )

        return BlendedRisk(
            score=score,
            band=band,
            tier=tier,
            tier_sensitivity=sensitivity,
            components=components,
            formula=FORMULA,
            explanation=explanation,
        )

    # -------------------------------------------------------------- routing
    @staticmethod
    def _route_approvals(
        outcomes: Sequence[PolicyOutcome], blended: BlendedRisk
    ) -> list[RequiredApprovalSpec]:
        by_level: dict[ApprovalLevel, RequiredApprovalSpec] = {}

        for outcome in outcomes:
            if not outcome.violated or outcome.required_action is None:
                continue
            spec = by_level.get(outcome.required_action)
            if spec is None:
                spec = RequiredApprovalSpec(
                    level=outcome.required_action, reason="", triggered_by=[]
                )
                by_level[outcome.required_action] = spec
            spec.triggered_by.append(outcome.reason)

        threshold = settings.risk_finance_escalation_threshold
        if blended.score >= threshold:
            spec = by_level.setdefault(
                ApprovalLevel.FINANCE,
                RequiredApprovalSpec(level=ApprovalLevel.FINANCE, reason=""),
            )
            spec.triggered_by.append(
                f"Blended risk score {_trim(blended.score)} reached the "
                f"{_trim(threshold)} finance escalation threshold."
            )

        for level, spec in by_level.items():
            count = len(spec.triggered_by)
            spec.reason = (
                f"{_level_label(level)} approval required: {spec.triggered_by[0]}"
                if count == 1
                else (
                    f"{_level_label(level)} approval required for {count} reasons: "
                    + " ".join(spec.triggered_by)
                )
            )

        return sorted(by_level.values(), key=lambda s: APPROVAL_LEVEL_ORDER[s.level])

    # ---------------------------------------------------------- persistence
    @classmethod
    async def evaluate_and_persist(
        cls,
        session: AsyncSession,
        version: QuoteVersion,
        *,
        lines: Sequence[QuoteLine] | None = None,
        profile: CustomerProfile | None = None,
    ) -> PolicyEvaluation:
        """Evaluate, replace stored results, and stamp the version's risk."""
        from app.services.commercial_engine import CommercialEngine  # noqa: F811

        if lines is None:
            lines = await CommercialEngine.load_lines(session, version.id)
        if profile is None:
            profile = await CommercialEngine._customer_profile_for_version(
                session, version
            )
        policies = await cls.active_policies(session, version.organization_id)

        evaluation = cls.evaluate(
            version=version, lines=lines, profile=profile, policies=policies
        )

        await session.execute(
            delete(PolicyResult).where(PolicyResult.quote_version_id == version.id)
        )
        for outcome in evaluation.outcomes:
            session.add(
                PolicyResult(
                    organization_id=version.organization_id,
                    quote_version_id=version.id,
                    policy_id=outcome.policy_id,
                    quote_line_id=outcome.quote_line_id,
                    rule=outcome.rule,
                    status=outcome.status,
                    subject=outcome.subject,
                    actual_value=outcome.actual_value,
                    threshold_value=outcome.threshold_value,
                    overage_points=outcome.overage_points,
                    unit=outcome.unit,
                    scope_category=outcome.scope_category,
                    scope_tier=outcome.scope_tier,
                    reason=outcome.reason,
                    required_action=outcome.required_action,
                    severity=outcome.severity,
                    risk_contribution=outcome.risk_contribution,
                    detail=outcome.detail,
                    evaluated_at=evaluation.evaluated_at,
                )
            )

        version.blended_risk_score = evaluation.blended_risk.score
        version.risk_band = evaluation.blended_risk.band
        version.requires_approval = evaluation.requires_approval
        await session.flush()

        # The snapshot is written by the CommercialEngine before risk is known,
        # so back-fill the score. A snapshot with a stale risk figure would
        # misrepresent what the approver was actually looking at.
        snapshot = await CommercialEngine.current_snapshot(session, version.id)
        if snapshot is not None:
            snapshot.blended_risk_score = evaluation.blended_risk.score
            snapshot.snapshot_json = {
                **snapshot.snapshot_json,
                "blended_risk": evaluation.blended_risk.as_dict(),
                "policy_violations": [o.as_dict() for o in evaluation.violations],
                "required_approvals": [
                    r.as_dict() for r in evaluation.required_approvals
                ],
            }
            await session.flush()

        return evaluation

    @staticmethod
    async def stored_results(
        session: AsyncSession, version_id: uuid.UUID
    ) -> list[PolicyResult]:
        result = await session.execute(
            select(PolicyResult)
            .where(PolicyResult.quote_version_id == version_id)
            .order_by(PolicyResult.status, PolicyResult.rule)
        )
        return list(result.scalars())


# ------------------------------------------------------------------ helpers
def _band_for(score: Decimal) -> RiskBand:
    if score <= ZERO:
        return RiskBand.NONE
    if score < Decimal("15"):
        return RiskBand.LOW
    if score < Decimal("40"):
        return RiskBand.MEDIUM
    if score < Decimal("70"):
        return RiskBand.HIGH
    return RiskBand.CRITICAL


def _trim(value: Decimal) -> str:
    """Render a Decimal without trailing zero noise: 18.0000 -> '18'."""
    normalized = Decimal(value).normalize()
    if normalized == normalized.to_integral_value():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _level_label(level: ApprovalLevel) -> str:
    return {
        ApprovalLevel.SALES_MANAGER: "Sales Manager",
        ApprovalLevel.FINANCE: "Finance",
        ApprovalLevel.EXECUTIVE: "Executive",
    }[level]


def _terms_days(version: QuoteVersion) -> int:
    from app.enums import PaymentTerms

    return {
        PaymentTerms.PREPAID: 0,
        PaymentTerms.NET_15: 15,
        PaymentTerms.NET_30: 30,
        PaymentTerms.NET_45: 45,
        PaymentTerms.NET_60: 60,
        PaymentTerms.NET_90: 90,
    }[version.payment_terms]
