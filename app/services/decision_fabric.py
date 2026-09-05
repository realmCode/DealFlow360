"""DecisionFabric — the central business logic.

Runs on **every** revision, with no exceptions. Given two quote versions it
answers, in one structured result:

    what changed -> did it matter -> which policies now fire ->
    whose earlier decision is no longer valid -> who must act next

Materiality is **fail-closed**: a field on the material list counts as material
unless it moved by less than an explicit epsilon. Governance failures should be
false positives (an unnecessary re-approval), never false negatives (an order
shipped on a decision nobody actually made).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    ApprovalLevel,
    AttentionItemType,
    PolicyResultStatus,
    QuoteVersionSource,
    RoleCode,
    Severity,
)
from app.events import EventType
from app.models.customer_profile import CustomerProfile
from app.models.decision_impact import DecisionImpact
from app.models.quote import Quote
from app.models.quote_line import QuoteLine
from app.models.quote_version import QuoteVersion
from app.models.user import User
from app.services.audit_service import AttentionService, AuditService, jsonable
from app.services.commercial_engine import (
    CommercialEngine,
    ZERO,
    format_quantity as _qty,
    money,
    pct,
)
from app.services.policy_engine import PolicyEngine, PolicyEvaluation, _trim

# --------------------------------------------------------------- materiality
#: Fields whose change can invalidate a commercial decision.
MATERIAL_LINE_FIELDS = (
    "product_id",
    "quantity",
    "unit_list_price",
    "discount_pct",
    "recurring_periods",
    "recurring_interval",
)
MATERIAL_VERSION_FIELDS = (
    "payment_terms",
    "margin_pct",
    "total_revenue",
    "effective_discount_pct",
    "required_approvals",
)
#: Descriptive-only fields: recorded as changes, never material.
COSMETIC_LINE_FIELDS = ("description", "notes")

#: Movements below these are treated as noise rather than decisions.
DISCOUNT_EPSILON = Decimal("0.01")  # percentage points
MARGIN_EPSILON = Decimal("0.10")  # percentage points
REVENUE_EPSILON_PCT = Decimal("0.10")  # % of previous revenue
QUANTITY_EPSILON = Decimal("0")  # any quantity change matters

#: Above this discount movement the change is treated as high severity.
DISCOUNT_HIGH_SEVERITY_POINTS = Decimal("5")
QUANTITY_HIGH_SEVERITY_RATIO = Decimal("10")  # percent


@dataclass(slots=True)
class ChangeRecord:
    field_name: str
    old_value: Any
    new_value: Any
    material: bool
    severity: Severity
    reason: str
    subject: str | None = None
    quote_line_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    action_required: str | None = None
    affected_entity_type: str | None = None
    affected_entity_id: uuid.UUID | None = None

    def as_change_dict(self) -> dict[str, Any]:
        return {
            "field": self.field_name,
            "subject": self.subject,
            "quote_line_id": self.quote_line_id,
            "old_value": jsonable(self.old_value),
            "new_value": jsonable(self.new_value),
            "material": self.material,
        }

    def as_material_dict(self) -> dict[str, Any]:
        return {
            "field": self.field_name,
            "subject": self.subject,
            "quote_line_id": self.quote_line_id,
            "old": jsonable(self.old_value),
            "new": jsonable(self.new_value),
            "severity": self.severity,
            "reason": self.reason,
        }


@dataclass(slots=True)
class StaleDecisionRecord:
    approval_request_id: uuid.UUID
    previous_decision: str
    reason: str
    decided_at: datetime | None = None
    decided_by: str | None = None


@dataclass(slots=True)
class FabricOutcome:
    """Everything the Decision Fabric concluded about one revision."""

    quote_id: uuid.UUID
    quote_version_id: uuid.UUID
    previous_version_id: uuid.UUID | None
    evaluated_at: datetime
    changes: list[ChangeRecord] = field(default_factory=list)
    evaluation: PolicyEvaluation | None = None
    stale_decisions: list[StaleDecisionRecord] = field(default_factory=list)
    affected_entities: list[dict[str, Any]] = field(default_factory=list)
    attention_drafts: list[dict[str, Any]] = field(default_factory=list)
    explanation: dict[str, Any] = field(default_factory=dict)
    new_approval_request_id: uuid.UUID | None = None

    @property
    def material_changes(self) -> list[ChangeRecord]:
        return [c for c in self.changes if c.material]

    @property
    def has_material_change(self) -> bool:
        return any(c.material for c in self.changes)


class DecisionFabric:
    # ---------------------------------------------------- change detection
    @classmethod
    def detect_changes(
        cls,
        *,
        previous: QuoteVersion | None,
        previous_lines: Sequence[QuoteLine],
        current: QuoteVersion,
        current_lines: Sequence[QuoteLine],
        previous_approvals: Sequence[ApprovalLevel] | None = None,
        current_approvals: Sequence[ApprovalLevel] = (),
        margin_floor: Decimal | None = None,
    ) -> list[ChangeRecord]:
        """Compare two versions field by field. Pure — no I/O."""
        if previous is None:
            return []

        changes: list[ChangeRecord] = []
        changes.extend(cls._compare_lines(previous_lines, current_lines))
        changes.extend(
            cls._compare_version(
                previous,
                current,
                previous_approvals=previous_approvals,
                current_approvals=current_approvals,
                margin_floor=margin_floor,
            )
        )
        return changes

    @staticmethod
    def _pair_lines(
        previous_lines: Sequence[QuoteLine], current_lines: Sequence[QuoteLine]
    ) -> list[tuple[int, QuoteLine | None, QuoteLine | None]]:
        """Pair a revision's lines with the parent lines they came from.

        Matching is by ``source_line_id`` provenance. Falling back to
        ``line_number`` would report "line 4 removed, new line added" as a
        single product swap, which is a different — and much less alarming —
        story than the truth.
        """
        by_source = {
            line.source_line_id: line
            for line in current_lines
            if line.source_line_id is not None
        }
        matched_current: set[uuid.UUID] = set()
        pairs: list[tuple[int, QuoteLine | None, QuoteLine | None]] = []

        for old in previous_lines:
            new = by_source.get(old.id)
            if new is None and not by_source:
                # Legacy rows written before provenance was tracked.
                new = next(
                    (
                        line
                        for line in current_lines
                        if line.line_number == old.line_number
                        and line.id not in matched_current
                    ),
                    None,
                )
            if new is not None:
                matched_current.add(new.id)
            pairs.append((old.line_number, old, new))

        for line in current_lines:
            if line.id not in matched_current:
                pairs.append((line.line_number, None, line))

        return sorted(pairs, key=lambda p: p[0])

    @classmethod
    def _compare_lines(
        cls,
        previous_lines: Sequence[QuoteLine],
        current_lines: Sequence[QuoteLine],
    ) -> list[ChangeRecord]:
        changes: list[ChangeRecord] = []

        for num, old, new in cls._pair_lines(previous_lines, current_lines):
            if old is None and new is not None:
                changes.append(
                    ChangeRecord(
                        field_name="line_added",
                        old_value=None,
                        new_value={
                            "description": new.description,
                            "quantity": str(new.quantity),
                            "discount_pct": str(pct(new.discount_pct)),
                            "net_amount": str(money(new.net_amount)),
                        },
                        material=True,
                        severity=Severity.HIGH,
                        subject=new.description,
                        quote_line_id=new.id,
                        product_id=new.product_id,
                        reason=(
                            f"Line {num} '{new.description}' was added, changing the "
                            f"scope of the quote by "
                            f"{money(new.net_amount)} in net revenue."
                        ),
                        action_required="REEVALUATE_POLICY",
                    )
                )
                continue

            if new is None and old is not None:
                changes.append(
                    ChangeRecord(
                        field_name="line_removed",
                        old_value={
                            "description": old.description,
                            "quantity": str(old.quantity),
                            "net_amount": str(money(old.net_amount)),
                        },
                        new_value=None,
                        material=True,
                        severity=Severity.HIGH,
                        subject=old.description,
                        quote_line_id=old.id,
                        product_id=old.product_id,
                        reason=(
                            f"Line {num} '{old.description}' was removed, reducing "
                            f"net revenue by {money(old.net_amount)}."
                        ),
                        action_required="REEVALUATE_POLICY",
                    )
                )
                continue

            assert old is not None and new is not None

            if old.product_id != new.product_id:
                changes.append(
                    ChangeRecord(
                        field_name="product",
                        old_value=str(old.product_id),
                        new_value=str(new.product_id),
                        material=True,
                        severity=Severity.HIGH,
                        subject=new.description,
                        quote_line_id=new.id,
                        product_id=new.product_id,
                        reason=(
                            f"Line {num} was switched from '{old.description}' to "
                            f"'{new.description}', which changes cost, category "
                            f"and the applicable discount ceiling."
                        ),
                        action_required="REEVALUATE_POLICY",
                    )
                )

            if old.quantity != new.quantity:
                delta = Decimal(new.quantity) - Decimal(old.quantity)
                ratio = (
                    abs(delta) / Decimal(old.quantity) * Decimal("100")
                    if Decimal(old.quantity) != ZERO
                    else Decimal("100")
                )
                severity = (
                    Severity.HIGH
                    if ratio >= QUANTITY_HIGH_SEVERITY_RATIO
                    else Severity.MEDIUM
                )
                changes.append(
                    ChangeRecord(
                        field_name="quantity",
                        old_value=str(old.quantity),
                        new_value=str(new.quantity),
                        material=True,
                        severity=severity,
                        subject=new.description,
                        quote_line_id=new.id,
                        product_id=new.product_id,
                        reason=(
                            f"Quantity of '{new.description}' changed from "
                            f"{_qty(old.quantity)} to {_qty(new.quantity)} "
                            f"({'+' if delta > 0 else ''}{_qty(delta)}, "
                            f"{_trim(pct(ratio))}%), which changes revenue and the "
                            f"stock that must be allocated."
                        ),
                        action_required="REEVALUATE_POLICY",
                    )
                )

            if Decimal(old.unit_list_price) != Decimal(new.unit_list_price):
                changes.append(
                    ChangeRecord(
                        field_name="unit_price",
                        old_value=str(old.unit_list_price),
                        new_value=str(new.unit_list_price),
                        material=True,
                        severity=Severity.HIGH,
                        subject=new.description,
                        quote_line_id=new.id,
                        product_id=new.product_id,
                        reason=(
                            f"Unit price of '{new.description}' changed from "
                            f"{old.unit_list_price} to {new.unit_list_price}, "
                            f"directly changing revenue and margin."
                        ),
                        action_required="REEVALUATE_POLICY",
                    )
                )

            old_disc = pct(old.discount_pct)
            new_disc = pct(new.discount_pct)
            if abs(new_disc - old_disc) > DISCOUNT_EPSILON:
                delta = new_disc - old_disc
                severity = (
                    Severity.HIGH
                    if abs(delta) >= DISCOUNT_HIGH_SEVERITY_POINTS
                    else Severity.MEDIUM
                )
                direction = "increased" if delta > 0 else "decreased"
                changes.append(
                    ChangeRecord(
                        field_name="discount_pct",
                        old_value=str(old_disc),
                        new_value=str(new_disc),
                        material=True,
                        severity=severity,
                        subject=new.description,
                        quote_line_id=new.id,
                        product_id=new.product_id,
                        reason=(
                            f"Discount on '{new.description}' {direction} from "
                            f"{_trim(old_disc)}% to {_trim(new_disc)}% "
                            f"({'+' if delta > 0 else ''}{_trim(delta)} percentage "
                            f"points), which must be re-checked against the "
                            f"category ceiling."
                        ),
                        action_required="REEVALUATE_POLICY",
                    )
                )

            if old.recurring_periods != new.recurring_periods:
                changes.append(
                    ChangeRecord(
                        field_name="recurring_quantity",
                        old_value=old.recurring_periods,
                        new_value=new.recurring_periods,
                        material=True,
                        severity=Severity.MEDIUM,
                        subject=new.description,
                        quote_line_id=new.id,
                        product_id=new.product_id,
                        reason=(
                            f"Subscription term for '{new.description}' changed from "
                            f"{old.recurring_periods} to {new.recurring_periods} "
                            f"periods, changing contract value and the billing "
                            f"schedule."
                        ),
                        action_required="REBUILD_BILLING",
                    )
                )

            if old.recurring_interval != new.recurring_interval:
                changes.append(
                    ChangeRecord(
                        field_name="subscription_plan",
                        old_value=(
                            old.recurring_interval.value
                            if old.recurring_interval
                            else None
                        ),
                        new_value=(
                            new.recurring_interval.value
                            if new.recurring_interval
                            else None
                        ),
                        material=True,
                        severity=Severity.MEDIUM,
                        subject=new.description,
                        quote_line_id=new.id,
                        product_id=new.product_id,
                        reason=(
                            f"Billing interval for '{new.description}' changed, "
                            f"which rebuilds the recurring billing schedule."
                        ),
                        action_required="REBUILD_BILLING",
                    )
                )

            for cosmetic in COSMETIC_LINE_FIELDS:
                old_v = getattr(old, cosmetic, None)
                new_v = getattr(new, cosmetic, None)
                if old_v != new_v:
                    changes.append(
                        ChangeRecord(
                            field_name=cosmetic,
                            old_value=old_v,
                            new_value=new_v,
                            material=False,
                            severity=Severity.LOW,
                            subject=new.description,
                            quote_line_id=new.id,
                            product_id=new.product_id,
                            reason=(
                                f"The {cosmetic} of line {num} changed. This is "
                                f"descriptive only and does not affect any "
                                f"commercial decision."
                            ),
                        )
                    )

        return changes

    @staticmethod
    def _compare_version(
        previous: QuoteVersion,
        current: QuoteVersion,
        *,
        previous_approvals: Sequence[ApprovalLevel] | None,
        current_approvals: Sequence[ApprovalLevel],
        margin_floor: Decimal | None,
    ) -> list[ChangeRecord]:
        changes: list[ChangeRecord] = []

        if previous.payment_terms != current.payment_terms:
            changes.append(
                ChangeRecord(
                    field_name="payment_terms",
                    old_value=previous.payment_terms.value,
                    new_value=current.payment_terms.value,
                    material=True,
                    severity=Severity.HIGH,
                    subject="Payment terms",
                    reason=(
                        f"Payment terms changed from "
                        f"{previous.payment_terms.value.replace('_', ' ')} to "
                        f"{current.payment_terms.value.replace('_', ' ')}, changing "
                        f"cash-flow exposure and credit risk."
                    ),
                    action_required="REEVALUATE_POLICY",
                )
            )

        old_margin = pct(previous.margin_pct or ZERO)
        new_margin = pct(current.margin_pct or ZERO)
        if abs(new_margin - old_margin) > MARGIN_EPSILON:
            crossed_floor = (
                margin_floor is not None
                and old_margin >= margin_floor
                and new_margin < margin_floor
            )
            severity = (
                Severity.CRITICAL
                if crossed_floor
                else (Severity.HIGH if new_margin < old_margin else Severity.MEDIUM)
            )
            reason = (
                f"Margin moved from {_trim(old_margin)}% to {_trim(new_margin)}% "
                f"({'+' if new_margin > old_margin else ''}"
                f"{_trim(new_margin - old_margin)} percentage points)."
            )
            if crossed_floor:
                reason += (
                    f" This crosses the {_trim(margin_floor)}% minimum margin floor, "
                    f"so the deal no longer satisfies the policy it was approved "
                    f"under."
                )
            changes.append(
                ChangeRecord(
                    field_name="margin_pct",
                    old_value=str(old_margin),
                    new_value=str(new_margin),
                    material=True,
                    severity=severity,
                    subject="Quote margin",
                    reason=reason,
                    action_required="FINANCE_REVIEW" if crossed_floor else None,
                )
            )

        old_rev = money(previous.total_revenue or ZERO)
        new_rev = money(current.total_revenue or ZERO)
        if old_rev != new_rev:
            ratio = (
                abs(new_rev - old_rev) / old_rev * Decimal("100")
                if old_rev != ZERO
                else Decimal("100")
            )
            material = ratio > REVENUE_EPSILON_PCT
            changes.append(
                ChangeRecord(
                    field_name="total_revenue",
                    old_value=str(old_rev),
                    new_value=str(new_rev),
                    material=material,
                    severity=Severity.MEDIUM if material else Severity.LOW,
                    subject="Quote total",
                    reason=(
                        f"Total revenue moved from {old_rev} to {new_rev} "
                        f"({_trim(pct(ratio))}%)."
                        + (
                            ""
                            if material
                            else " This is below the "
                            f"{_trim(REVENUE_EPSILON_PCT)}% materiality threshold and "
                            "does not invalidate prior decisions."
                        )
                    ),
                )
            )

        old_eff = pct(previous.effective_discount_pct or ZERO)
        new_eff = pct(current.effective_discount_pct or ZERO)
        if abs(new_eff - old_eff) > DISCOUNT_EPSILON:
            changes.append(
                ChangeRecord(
                    field_name="effective_discount_pct",
                    old_value=str(old_eff),
                    new_value=str(new_eff),
                    material=True,
                    severity=Severity.MEDIUM,
                    subject="Blended discount",
                    reason=(
                        f"Blended discount across the quote moved from "
                        f"{_trim(old_eff)}% to {_trim(new_eff)}%."
                    ),
                )
            )

        # `None` means the previous version was never submitted, so it had no
        # routing decision that could have changed.
        if previous_approvals is None:
            return changes

        prev_set = {a.value for a in previous_approvals}
        curr_set = {a.value for a in current_approvals}
        if prev_set != curr_set:
            added = sorted(curr_set - prev_set)
            removed = sorted(prev_set - curr_set)
            bits: list[str] = []
            if added:
                bits.append(f"now also requires {', '.join(added)}")
            if removed:
                bits.append(f"no longer requires {', '.join(removed)}")
            changes.append(
                ChangeRecord(
                    field_name="required_approvals",
                    old_value=sorted(prev_set),
                    new_value=sorted(curr_set),
                    material=True,
                    severity=Severity.HIGH if added else Severity.MEDIUM,
                    subject="Approval routing",
                    reason=(
                        "Policy evaluation changed the approval requirement: "
                        + " and ".join(bits)
                        + "."
                    ),
                    action_required="REROUTE_APPROVAL",
                )
            )

        return changes

    # -------------------------------------------------- orchestrated entry
    @classmethod
    async def process_version(
        cls,
        session: AsyncSession,
        *,
        version: QuoteVersion,
        actor: User | None,
        previous_version: QuoteVersion | None = None,
        trigger: str = "REVISION",
        create_approval: bool = True,
    ) -> FabricOutcome:
        """Recalculate, evaluate, diff, invalidate, and explain — atomically.

        Called on submit, on every revision and on every customer counter.
        """
        from app.services.approval_service import ApprovalService

        quote = await session.get(Quote, version.quote_id)
        assert quote is not None
        profile = await CommercialEngine._customer_profile_for_version(session, version)

        current_lines = await CommercialEngine.load_lines(session, version.id)
        await CommercialEngine.calculate_version(
            session, version, lines=current_lines, persist_snapshot=True
        )
        evaluation = await PolicyEngine.evaluate_and_persist(
            session, version, lines=current_lines, profile=profile
        )

        previous_lines: list[QuoteLine] = []
        previous_approvals: list[ApprovalLevel] | None = None
        margin_floor = _margin_floor_from(evaluation)

        if previous_version is None and version.parent_version_id:
            previous_version = await session.get(
                QuoteVersion, version.parent_version_id
            )
        if previous_version is not None:
            previous_lines = await CommercialEngine.load_lines(
                session, previous_version.id
            )
            previous_approvals = await ApprovalService.required_levels_for_version(
                session, previous_version.id
            )

        changes = cls.detect_changes(
            previous=previous_version,
            previous_lines=previous_lines,
            current=version,
            current_lines=current_lines,
            previous_approvals=previous_approvals,
            current_approvals=[r.level for r in evaluation.required_approvals],
            margin_floor=margin_floor,
        )

        outcome = FabricOutcome(
            quote_id=version.quote_id,
            quote_version_id=version.id,
            previous_version_id=previous_version.id if previous_version else None,
            evaluated_at=evaluation.evaluated_at,
            changes=changes,
            evaluation=evaluation,
        )

        await AuditService.emit(
            session,
            EventType.POLICY_EVALUATED,
            organization_id=version.organization_id,
            entity_type="quote_version",
            entity_id=version.id,
            actor=actor,
            payload={
                "version_number": version.version_number,
                "trigger": trigger,
                "blended_risk_score": str(evaluation.blended_risk.score),
                "risk_band": evaluation.blended_risk.band.value,
                "violation_count": len(evaluation.violations),
                "required_approvals": [
                    r.level.value for r in evaluation.required_approvals
                ],
                "risk_explanation": evaluation.blended_risk.explanation,
            },
        )

        # ------------------------------------------- persist decision impacts
        for change in changes:
            session.add(
                DecisionImpact(
                    organization_id=version.organization_id,
                    quote_id=version.quote_id,
                    quote_version_id=version.id,
                    previous_version_id=(
                        previous_version.id if previous_version else None
                    ),
                    quote_line_id=change.quote_line_id,
                    product_id=change.product_id,
                    changed_field=change.field_name,
                    subject=change.subject,
                    old_value=jsonable(change.old_value),
                    new_value=jsonable(change.new_value),
                    material=change.material,
                    severity=change.severity,
                    change_reason=change.reason,
                    affected_entity_type=change.affected_entity_type,
                    affected_entity_id=change.affected_entity_id,
                    action_required=change.action_required,
                    detected_at=evaluation.evaluated_at,
                )
            )
        if changes:
            await session.flush()

        material = outcome.material_changes
        if material:
            await AuditService.emit(
                session,
                EventType.MATERIAL_CHANGE_DETECTED,
                organization_id=version.organization_id,
                entity_type="quote_version",
                entity_id=version.id,
                actor=actor,
                payload={
                    "version_number": version.version_number,
                    "previous_version_id": (
                        str(previous_version.id) if previous_version else None
                    ),
                    "material_change_count": len(material),
                    "changes": [
                        {
                            "field": c.field_name,
                            "subject": c.subject,
                            "old": jsonable(c.old_value),
                            "new": jsonable(c.new_value),
                            "severity": c.severity.value,
                            "reason": c.reason,
                        }
                        for c in material
                    ],
                },
            )

            stale = await ApprovalService.invalidate_prior_approvals(
                session,
                quote_id=version.quote_id,
                new_version=version,
                actor=actor,
                material_changes=[c.as_material_dict() for c in material],
            )
            outcome.stale_decisions = stale
            for record in stale:
                outcome.affected_entities.append(
                    {
                        "type": "approval_request",
                        "id": record.approval_request_id,
                        "reason": record.reason,
                    }
                )

        # --------------------------------------------------- new approval req
        if create_approval and evaluation.requires_approval:
            request = await ApprovalService.open_request(
                session,
                version=version,
                evaluation=evaluation,
                actor=actor,
                is_reapproval=bool(outcome.stale_decisions),
                supersedes=[r.approval_request_id for r in outcome.stale_decisions],
            )
            if request is not None:
                outcome.new_approval_request_id = request.id
                outcome.affected_entities.append(
                    {
                        "type": "approval_request",
                        "id": request.id,
                        "reason": "New approval request opened for this version.",
                    }
                )

        if outcome.stale_decisions:
            version.is_stale = True
            version.stale_reason = (
                "A material change invalidated a previous approval. "
                + material[0].reason
            )
        await session.flush()

        outcome.attention_drafts = await cls._raise_attention_items(
            session,
            version=version,
            quote=quote,
            profile=profile,
            evaluation=evaluation,
            outcome=outcome,
            actor=actor,
        )
        outcome.explanation = cls._explain(
            version=version,
            previous_version=previous_version,
            changes=changes,
            evaluation=evaluation,
            outcome=outcome,
            trigger=trigger,
        )
        return outcome

    # ------------------------------------------------------ attention items
    #
    # Raised only from `process_version` — i.e. on submit, revision and
    # customer counter. A draft being priced is not asking anyone for a
    # decision yet, so recalculating it must not put items in front of an
    # operator; the Control Tower would become unreadable within minutes.
    @classmethod
    async def _raise_attention_items(
        cls,
        session: AsyncSession,
        *,
        version: QuoteVersion,
        quote: Quote,
        profile: CustomerProfile | None,
        evaluation: PolicyEvaluation,
        outcome: FabricOutcome,
        actor: User | None,
    ) -> list[dict[str, Any]]:
        drafts: list[dict[str, Any]] = []
        customer = profile.display_name if profile else "the customer"
        label = f"{quote.quote_number} v{version.version_number}"

        for record in outcome.stale_decisions:
            title = f"Approval invalidated on {label}"
            draft = {
                "type": AttentionItemType.STALE_APPROVAL.value,
                "severity": Severity.CRITICAL.value,
                "title": title,
                "reason": record.reason,
                "impact": (
                    f"The order for {customer} cannot proceed: confirmation is "
                    f"blocked until this quote is approved again."
                ),
                "owner_role": RoleCode.FINANCE.value,
                "recommended_action": (
                    f"Review revised quote {label} and either re-approve it or "
                    f"request a further revision."
                ),
            }
            drafts.append(draft)
            await AttentionService.upsert(
                session,
                organization_id=version.organization_id,
                source_type="approval_request",
                source_id=record.approval_request_id,
                item_type=AttentionItemType.STALE_APPROVAL,
                severity=Severity.CRITICAL,
                title=title,
                reason=record.reason,
                impact=draft["impact"],
                owner_role=RoleCode.FINANCE,
                recommended_action=draft["recommended_action"],
                deal_id=quote.deal_id,
                quote_id=quote.id,
                detail={
                    "quote_version_id": str(version.id),
                    "previous_decision": record.previous_decision,
                    "blended_risk_score": str(evaluation.blended_risk.score),
                },
                actor=actor,
            )

        margin_violation = next(
            (
                o
                for o in evaluation.outcomes
                if o.rule == "MIN_MARGIN" and o.status is PolicyResultStatus.VIOLATED
            ),
            None,
        )
        if margin_violation is not None:
            title = f"Margin below floor on {label}"
            impact = (
                f"Revenue of {money(version.net_revenue)} yields only "
                f"{_trim(pct(version.margin_pct))}% margin; the deal is unprofitable "
                f"against policy and needs Finance sign-off."
            )
            action = (
                "Reduce discounts, re-price the low-margin lines, or accept the "
                "exception in writing."
            )
            drafts.append(
                {
                    "type": AttentionItemType.MARGIN_VIOLATION.value,
                    "severity": margin_violation.severity.value,
                    "title": title,
                    "reason": margin_violation.reason,
                    "impact": impact,
                    "owner_role": RoleCode.FINANCE.value,
                    "recommended_action": action,
                }
            )
            await AttentionService.upsert(
                session,
                organization_id=version.organization_id,
                source_type="quote_version",
                source_id=version.id,
                item_type=AttentionItemType.MARGIN_VIOLATION,
                severity=(
                    Severity.HIGH
                    if margin_violation.severity is Severity.MEDIUM
                    else margin_violation.severity
                ),
                title=title,
                reason=margin_violation.reason,
                impact=impact,
                owner_role=RoleCode.FINANCE,
                recommended_action=action,
                deal_id=quote.deal_id,
                quote_id=quote.id,
                detail={
                    "actual_margin_pct": str(margin_violation.actual_value),
                    "required_margin_pct": str(margin_violation.threshold_value),
                },
                actor=actor,
            )
        else:
            await AttentionService.resolve(
                session,
                organization_id=version.organization_id,
                source_type="quote_version",
                source_id=version.id,
                item_type=AttentionItemType.MARGIN_VIOLATION,
                note="Margin returned above the policy floor.",
                actor=actor,
            )

        return drafts

    # ----------------------------------------------------------- narrative
    @staticmethod
    def _explain(
        *,
        version: QuoteVersion,
        previous_version: QuoteVersion | None,
        changes: Sequence[ChangeRecord],
        evaluation: PolicyEvaluation,
        outcome: FabricOutcome,
        trigger: str,
    ) -> dict[str, Any]:
        material = [c for c in changes if c.material]
        violations = evaluation.violations
        chain: list[str] = []

        for change in material:
            if change.field_name == "discount_pct":
                chain.append(
                    f"Discount on {change.subject}: {_trim(Decimal(change.old_value))}% "
                    f"-> {_trim(Decimal(change.new_value))}%"
                )
            elif change.field_name == "margin_pct":
                chain.append(
                    f"Margin: {_trim(Decimal(change.old_value))}% -> "
                    f"{_trim(Decimal(change.new_value))}%"
                )
            elif change.field_name == "quantity":
                chain.append(
                    f"Quantity of {change.subject}: {change.old_value} -> "
                    f"{change.new_value}"
                )
            elif change.field_name == "required_approvals":
                chain.append(
                    f"Approval routing: {change.old_value or 'none'} -> "
                    f"{change.new_value or 'none'}"
                )
            else:
                chain.append(f"{change.field_name}: {change.subject or 'changed'}")

        for violation in violations:
            chain.append(f"{violation.rule} violated ({violation.reason})")
        for record in outcome.stale_decisions:
            chain.append(f"Previous approval {record.previous_decision} -> STALE")
        if outcome.new_approval_request_id is not None:
            levels = ", ".join(
                r.level.value for r in evaluation.required_approvals
            )
            chain.append(f"New approval request routed to {levels}")

        if not changes and previous_version is not None:
            summary = (
                f"No changes were detected between version "
                f"{previous_version.version_number} and "
                f"{version.version_number}; existing decisions remain valid."
            )
            what_changed = "Nothing."
            why = "There is no commercial difference to re-govern."
            who = "Nobody needs to act."
            next_step = "The quote can continue on its existing approvals."
        elif previous_version is None:
            summary = (
                f"Version {version.version_number} was evaluated for the first time: "
                f"{len(violations)} policy violation(s), blended risk "
                f"{_trim(evaluation.blended_risk.score)}/100 "
                f"({evaluation.blended_risk.band.value})."
            )
            what_changed = "This is the initial evaluation of the quote."
            why = (
                evaluation.blended_risk.explanation
                if violations
                else "All governance thresholds are satisfied."
            )
            who = (
                ", ".join(r.level.value for r in evaluation.required_approvals)
                if evaluation.required_approvals
                else "Nobody — no approval is required."
            )
            next_step = (
                "Await the approvals listed above before sending the quote."
                if evaluation.required_approvals
                else "The quote can be sent to the customer immediately."
            )
        else:
            headline_change = material[0].reason if material else changes[0].reason
            summary = (
                f"{_trigger_phrase(trigger)} produced version "
                f"{version.version_number} with {len(material)} material change(s). "
                + (
                    f"{len(outcome.stale_decisions)} previous approval(s) are now "
                    f"stale."
                    if outcome.stale_decisions
                    else "No previous approval was invalidated."
                )
            )
            what_changed = headline_change
            why = (
                " ".join(v.reason for v in violations)
                if violations
                else (
                    "The change is material, so any decision made against the "
                    "previous numbers can no longer be relied upon."
                )
            )
            who = (
                ", ".join(sorted({r.level.value for r in evaluation.required_approvals}))
                if evaluation.required_approvals
                else "Nobody — the revised quote is within policy."
            )
            next_step = (
                "Customer confirmation is blocked until the new approval is granted."
                if outcome.stale_decisions or evaluation.requires_approval
                else "The revised quote can proceed to confirmation."
            )

        return {
            "summary": summary,
            "causal_chain": chain,
            "what_changed": what_changed,
            "why_it_matters": why,
            "who_is_affected": who,
            "what_happens_next": next_step,
        }

    # --------------------------------------------------------- impact read
    @classmethod
    async def impact_for_version(
        cls, session: AsyncSession, version: QuoteVersion
    ) -> dict[str, Any]:
        """Read model for ``GET /quote-versions/{id}/impact``.

        Rebuilt from persisted ``decision_impacts`` + ``policy_results`` so the
        endpoint is a pure read and never mutates state.
        """
        from app.services.approval_service import ApprovalService

        impacts = list(
            (
                await session.execute(
                    select(DecisionImpact)
                    .where(DecisionImpact.quote_version_id == version.id)
                    .order_by(DecisionImpact.detected_at, DecisionImpact.changed_field)
                )
            ).scalars()
        )
        results = await PolicyEngine.stored_results(session, version.id)
        stale = await ApprovalService.stale_records_for_quote(session, version.quote_id)
        pending = await ApprovalService.latest_request_for_version(session, version.id)

        previous_version = (
            await session.get(QuoteVersion, version.parent_version_id)
            if version.parent_version_id
            else None
        )

        changes = [
            {
                "field": i.changed_field,
                "subject": i.subject,
                "quote_line_id": i.quote_line_id,
                "old_value": i.old_value,
                "new_value": i.new_value,
                "material": i.material,
            }
            for i in impacts
        ]
        material_changes = [
            {
                "field": i.changed_field,
                "subject": i.subject,
                "quote_line_id": i.quote_line_id,
                "old": i.old_value,
                "new": i.new_value,
                "severity": i.severity,
                "reason": i.change_reason,
            }
            for i in impacts
            if i.material
        ]

        affected: list[dict[str, Any]] = []
        for i in impacts:
            if i.affected_entity_type and i.affected_entity_id:
                affected.append(
                    {
                        "type": i.affected_entity_type,
                        "id": i.affected_entity_id,
                        "reason": i.change_reason,
                    }
                )
        for record in stale:
            affected.append(
                {
                    "type": "approval_request",
                    "id": record.approval_request_id,
                    "reason": record.reason,
                }
            )
        if pending is not None:
            affected.append(
                {
                    "type": "approval_request",
                    "id": pending.id,
                    "reason": f"Approval request is {pending.status.value}.",
                }
            )

        required_approvals: list[dict[str, Any]] = []
        if pending is not None:
            for entry in pending.required_levels:
                required_approvals.append(
                    {
                        "type": entry.get("type"),
                        "reason": entry.get("reason", ""),
                        "triggered_by": entry.get("triggered_by", []),
                    }
                )

        attention_items = await cls._attention_drafts_for_quote(session, version)

        explanation = _explanation_from_storage(
            version=version,
            previous_version=previous_version,
            material_changes=material_changes,
            all_changes=changes,
            violations=[r for r in results if r.status is PolicyResultStatus.VIOLATED],
            stale=stale,
            pending=pending,
        )

        return {
            "quote_id": version.quote_id,
            "quote_version_id": version.id,
            "previous_version_id": version.parent_version_id,
            "evaluated_at": (
                results[0].evaluated_at if results else version.calculated_at
            )
            or datetime.now(UTC),
            "changes": changes,
            "material_changes": material_changes,
            "policy_results": results,
            "stale_decisions": [
                {
                    "approval_request_id": r.approval_request_id,
                    "previous_decision": r.previous_decision,
                    "reason": r.reason,
                    "decided_at": r.decided_at,
                    "decided_by": r.decided_by,
                }
                for r in stale
            ],
            "affected_entities": affected,
            "required_approvals": required_approvals,
            "attention_items": attention_items,
            "explanation": explanation,
            "has_material_change": bool(material_changes),
            "blocks_confirmation": version.is_stale
            or (pending is not None and pending.status.value == "PENDING"),
        }

    @staticmethod
    async def _attention_drafts_for_quote(
        session: AsyncSession, version: QuoteVersion
    ) -> list[dict[str, Any]]:
        from app.models.attention_item import AttentionItem
        from app.enums import AttentionItemStatus

        items = list(
            (
                await session.execute(
                    select(AttentionItem).where(
                        AttentionItem.quote_id == version.quote_id,
                        AttentionItem.status != AttentionItemStatus.RESOLVED,
                    )
                )
            ).scalars()
        )
        return [
            {
                "type": i.type.value,
                "severity": i.severity,
                "title": i.title,
                "reason": i.reason,
                "impact": i.impact,
                "owner_role": i.owner_role.value,
                "recommended_action": i.recommended_action,
            }
            for i in sorted(items, key=AttentionService.sort_key)
        ]


# ------------------------------------------------------------------ helpers
def _margin_floor_from(evaluation: PolicyEvaluation) -> Decimal | None:
    for outcome in evaluation.outcomes:
        if outcome.rule == "MIN_MARGIN":
            return pct(outcome.threshold_value)
    return None


def _trigger_phrase(trigger: str) -> str:
    return {
        "SUBMIT": "Submission for approval",
        "REVISION": "An internal revision",
        "CUSTOMER_COUNTER": "The customer's counter-offer",
        "APPROVER_REVISION_REQUEST": "An approver's revision request",
    }.get(trigger, "A revision")


_TRIGGER_BY_SOURCE: dict[QuoteVersionSource, str] = {
    QuoteVersionSource.INITIAL: "SUBMIT",
    QuoteVersionSource.INTERNAL_REVISION: "REVISION",
    QuoteVersionSource.CUSTOMER_COUNTER: "CUSTOMER_COUNTER",
    QuoteVersionSource.APPROVER_REVISION_REQUEST: "APPROVER_REVISION_REQUEST",
}


def _explanation_from_storage(
    *,
    version: QuoteVersion,
    previous_version: QuoteVersion | None,
    material_changes: Sequence[dict[str, Any]],
    all_changes: Sequence[dict[str, Any]],
    violations: Sequence[Any],
    stale: Sequence[StaleDecisionRecord],
    pending: Any,
) -> dict[str, Any]:
    chain: list[str] = []
    for change in material_changes:
        chain.append(
            f"{change['field']}"
            + (f" on {change['subject']}" if change.get("subject") else "")
            + f": {change.get('old')} -> {change.get('new')}"
        )
    for violation in violations:
        chain.append(f"{violation.rule} violated ({violation.reason})")
    for record in stale:
        chain.append(f"Previous approval {record.previous_decision} -> STALE")
    if pending is not None and pending.status.value == "PENDING":
        levels = ", ".join(e.get("type", "") for e in pending.required_levels)
        chain.append(f"Approval pending with {levels or 'approver'}")

    if not all_changes:
        return {
            "summary": (
                f"Version {version.version_number} has no recorded changes against a "
                f"previous version."
                if previous_version
                else f"Version {version.version_number} is the initial version."
            ),
            "causal_chain": chain,
            "what_changed": "Nothing." if previous_version else "Initial version.",
            "why_it_matters": (
                "No prior decision is affected."
                if not violations
                else " ".join(v.reason for v in violations)
            ),
            "who_is_affected": (
                "Nobody."
                if pending is None
                else ", ".join(e.get("type", "") for e in pending.required_levels)
            ),
            "what_happens_next": (
                "Awaiting approval."
                if pending is not None and pending.status.value == "PENDING"
                else "No action required."
            ),
        }

    # `quote_versions.source` records what caused this version to exist, so the
    # read path can reproduce the same narrative as the write path.
    trigger = _trigger_phrase(_TRIGGER_BY_SOURCE.get(version.source, "REVISION"))

    return {
        "summary": (
            f"{trigger} produced version {version.version_number} with "
            f"{len(material_changes)} material change(s) out of "
            f"{len(all_changes)} detected change(s). "
            + (
                f"{len(stale)} previous approval(s) were invalidated."
                if stale
                else "No previous approval was invalidated."
            )
        ),
        "causal_chain": chain,
        "what_changed": (
            material_changes[0]["reason"]
            if material_changes
            else "Only descriptive fields changed."
        ),
        "why_it_matters": (
            " ".join(v.reason for v in violations)
            if violations
            else (
                "The commercial basis of the quote moved, so prior decisions must be "
                "re-confirmed."
                if material_changes
                else "No governance threshold is affected."
            )
        ),
        "who_is_affected": (
            ", ".join(e.get("type", "") for e in pending.required_levels)
            if pending is not None and pending.required_levels
            else "Nobody needs to act."
        ),
        "what_happens_next": (
            "Customer confirmation is blocked until the new approval is granted."
            if version.is_stale
            or (pending is not None and pending.status.value == "PENDING")
            else "The quote can proceed."
        ),
    }
