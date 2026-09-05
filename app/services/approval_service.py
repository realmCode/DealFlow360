"""ApprovalService — routing, ordered steps, decisions and staleness.

Invariants enforced here (not in the router, not in the frontend):

* Approval steps are created from the PolicyEngine's routing decision.
* Nobody may approve a quote they raised or submitted — including a manager
  who happens to own the deal.
* A step that already carries a decision cannot be decided again.
* When a material change invalidates an approval, the old decision is *kept*
  and marked ``STALE``; history is never rewritten.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    APPROVAL_LEVEL_ORDER,
    APPROVAL_LEVEL_ROLE,
    ApprovalDecisionType,
    ApprovalLevel,
    ApprovalRequestStatus,
    ApprovalStepStatus,
    AttentionItemType,
    QuoteVersionStatus,
    RoleCode,
    Severity,
)
from app.errors import (
    AuthorizationError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
)
from app.events import EventType
from app.models.approval_decision import ApprovalDecision
from app.models.approval_request import ApprovalRequest
from app.models.approval_step import ApprovalStep
from app.models.quote import Quote
from app.models.quote_version import QuoteVersion
from app.models.user import User
from app.services.audit_service import AttentionService, AuditService, jsonable
from app.services.commercial_engine import money, pct
from app.services.decision_fabric import StaleDecisionRecord
from app.services.policy_engine import PolicyEvaluation, _level_label, _trim

OPEN_REQUEST_STATUSES = (ApprovalRequestStatus.PENDING,)


class ApprovalService:
    # ------------------------------------------------------------- queries
    @staticmethod
    async def latest_request_for_version(
        session: AsyncSession, version_id: uuid.UUID
    ) -> ApprovalRequest | None:
        result = await session.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.quote_version_id == version_id)
            .order_by(ApprovalRequest.created_at.desc())
        )
        return result.scalars().first()

    @staticmethod
    async def pending_request_for_version(
        session: AsyncSession, version_id: uuid.UUID
    ) -> ApprovalRequest | None:
        result = await session.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.quote_version_id == version_id,
                ApprovalRequest.status == ApprovalRequestStatus.PENDING,
            )
        )
        return result.scalars().first()

    @staticmethod
    async def steps_for_request(
        session: AsyncSession, request_id: uuid.UUID
    ) -> list[ApprovalStep]:
        result = await session.execute(
            select(ApprovalStep)
            .where(ApprovalStep.approval_request_id == request_id)
            .order_by(ApprovalStep.sequence)
        )
        return list(result.scalars())

    @staticmethod
    async def decisions_for_request(
        session: AsyncSession, request_id: uuid.UUID
    ) -> list[ApprovalDecision]:
        result = await session.execute(
            select(ApprovalDecision)
            .where(ApprovalDecision.approval_request_id == request_id)
            .order_by(ApprovalDecision.decided_at)
        )
        return list(result.scalars())

    @staticmethod
    async def required_levels_for_version(
        session: AsyncSession, version_id: uuid.UUID
    ) -> list[ApprovalLevel] | None:
        """The routing decision recorded for a version.

        Returns ``None`` when the version was never submitted, which is
        different from ``[]`` ("evaluated, and needs nobody"). The Decision
        Fabric relies on that distinction: comparing a fresh routing decision
        against a version that never had one would report a spurious material
        change on every first revision.
        """
        request = await ApprovalService.latest_request_for_version(session, version_id)
        if request is None:
            return None
        levels: list[ApprovalLevel] = []
        for entry in request.required_levels or []:
            raw = entry.get("type") if isinstance(entry, dict) else None
            if raw:
                try:
                    levels.append(ApprovalLevel(raw))
                except ValueError:
                    continue
        return levels

    @staticmethod
    async def stale_records_for_quote(
        session: AsyncSession, quote_id: uuid.UUID
    ) -> list[StaleDecisionRecord]:
        result = await session.execute(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.quote_id == quote_id,
                ApprovalRequest.status == ApprovalRequestStatus.STALE,
            )
            .order_by(ApprovalRequest.stale_at)
        )
        records: list[StaleDecisionRecord] = []
        for request in result.scalars():
            records.append(
                StaleDecisionRecord(
                    approval_request_id=request.id,
                    previous_decision=ApprovalRequestStatus.APPROVED.value,
                    reason=request.stale_reason or "Invalidated by a material change.",
                    decided_at=request.decided_at,
                )
            )
        return records

    # ------------------------------------------------------- open a request
    @classmethod
    async def open_request(
        cls,
        session: AsyncSession,
        *,
        version: QuoteVersion,
        evaluation: PolicyEvaluation,
        actor: User | None,
        is_reapproval: bool = False,
        supersedes: Sequence[uuid.UUID] = (),
    ) -> ApprovalRequest | None:
        """Create an approval request with one ordered step per required level.

        Returns ``None`` when policy evaluation requires no approval at all —
        the caller then treats the version as auto-approved.
        """
        if not evaluation.required_approvals:
            return None

        # Defensive: the partial unique index allows only one PENDING request
        # per version, so retire any straggler before inserting.
        existing = await cls.pending_request_for_version(session, version.id)
        if existing is not None:
            existing.status = ApprovalRequestStatus.CANCELLED
            existing.stale_reason = "Replaced by a re-evaluated approval request."
            for step in await cls.steps_for_request(session, existing.id):
                if step.status is ApprovalStepStatus.PENDING:
                    step.status = ApprovalStepStatus.SKIPPED
            await session.flush()

        levels = sorted(
            evaluation.required_approvals, key=lambda r: APPROVAL_LEVEL_ORDER[r.level]
        )
        headline = (
            "Re-approval required after a material change. "
            if is_reapproval
            else ""
        ) + " ".join(spec.reason for spec in levels)

        requester_id = actor.id if actor else version.created_by_user_id
        request = ApprovalRequest(
            organization_id=version.organization_id,
            quote_id=version.quote_id,
            quote_version_id=version.id,
            status=ApprovalRequestStatus.PENDING,
            requested_by_user_id=requester_id,
            reason=headline,
            required_levels=[spec.as_dict() for spec in levels],
            policy_summary=jsonable(evaluation.summary()),
            blended_risk_score=evaluation.blended_risk.score,
            current_step_sequence=1,
        )
        session.add(request)
        await session.flush()

        for index, spec in enumerate(levels, start=1):
            session.add(
                ApprovalStep(
                    organization_id=version.organization_id,
                    approval_request_id=request.id,
                    sequence=index,
                    level=spec.level,
                    required_role=APPROVAL_LEVEL_ROLE[spec.level],
                    status=ApprovalStepStatus.PENDING,
                    reason=spec.reason,
                )
            )
        await session.flush()

        for old_id in supersedes:
            old = await session.get(ApprovalRequest, old_id)
            if old is not None:
                old.superseded_by_request_id = request.id
        if supersedes:
            await session.flush()

        version.status = QuoteVersionStatus.PENDING_APPROVAL
        version.submitted_at = version.submitted_at or datetime.now(UTC)
        await session.flush()

        await AuditService.emit(
            session,
            EventType.APPROVAL_REQUESTED,
            organization_id=version.organization_id,
            entity_type="approval_request",
            entity_id=request.id,
            actor=actor,
            payload={
                "quote_version_id": str(version.id),
                "version_number": version.version_number,
                "is_reapproval": is_reapproval,
                "levels": [spec.level.value for spec in levels],
                "blended_risk_score": str(evaluation.blended_risk.score),
                "reason": headline,
            },
        )

        quote = await session.get(Quote, version.quote_id)
        first = levels[0]
        title = (
            f"{'Re-approval' if is_reapproval else 'Approval'} needed on "
            f"{quote.quote_number if quote else 'quote'} v{version.version_number}"
        )
        impact = (
            f"The quote cannot be sent or confirmed while this is outstanding. "
            f"Total {money(version.total_revenue)} at "
            f"{_trim(pct(version.margin_pct))}% margin."
        )
        await AttentionService.upsert(
            session,
            organization_id=version.organization_id,
            source_type="approval_request",
            source_id=request.id,
            item_type=AttentionItemType.PENDING_APPROVAL,
            severity=Severity.HIGH if is_reapproval else Severity.MEDIUM,
            title=title,
            reason=headline,
            impact=impact,
            owner_role=APPROVAL_LEVEL_ROLE[first.level],
            recommended_action=(
                f"Open the approval, review the policy findings and either approve, "
                f"reject, or request a revision."
            ),
            deal_id=quote.deal_id if quote else None,
            quote_id=version.quote_id,
            detail={
                "quote_version_id": str(version.id),
                "levels": [spec.level.value for spec in levels],
                "blended_risk_score": str(evaluation.blended_risk.score),
            },
            actor=actor,
        )
        return request

    # ------------------------------------------------- record auto-approval
    @classmethod
    async def record_auto_approval(
        cls,
        session: AsyncSession,
        *,
        version: QuoteVersion,
        evaluation: PolicyEvaluation,
        actor: User | None,
    ) -> ApprovalRequest:
        """Persist an approval record for a version that needed no human.

        Auto-approval is still a *decision* — made by the policy engine rather
        than a person. Recording it means "who approved this?" always has an
        answer, and means a later material change has something concrete to
        mark stale. Without this row, a clean quote that is later revised would
        silently lose the fact that its earlier approval no longer holds.

        The row carries zero steps, which is how it is distinguished from a
        human approval.
        """
        existing = await cls.latest_request_for_version(session, version.id)
        if existing is not None and existing.status is ApprovalRequestStatus.APPROVED:
            return existing

        now = datetime.now(UTC)
        reason = (
            "Auto-approved: no policy was violated and the blended risk score is "
            f"{_trim(evaluation.blended_risk.score)}, so no human approval is "
            "required."
        )
        request = ApprovalRequest(
            organization_id=version.organization_id,
            quote_id=version.quote_id,
            quote_version_id=version.id,
            status=ApprovalRequestStatus.APPROVED,
            requested_by_user_id=(
                actor.id if actor else version.created_by_user_id
            ),
            reason=reason,
            required_levels=[],
            policy_summary=jsonable(evaluation.summary()),
            blended_risk_score=evaluation.blended_risk.score,
            current_step_sequence=1,
            decided_at=now,
        )
        session.add(request)
        await session.flush()
        return request

    # ------------------------------------------------------ mark stale
    @classmethod
    async def invalidate_prior_approvals(
        cls,
        session: AsyncSession,
        *,
        quote_id: uuid.UUID,
        new_version: QuoteVersion,
        actor: User | None,
        material_changes: Sequence[dict[str, Any]],
    ) -> list[StaleDecisionRecord]:
        """Invalidate decisions that were made against superseded numbers.

        ``APPROVED`` requests become ``STALE`` (the decision existed and is now
        void). ``PENDING`` requests on superseded versions become ``CANCELLED``
        (no decision was ever made, so there is nothing to invalidate).
        """
        result = await session.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.quote_id == quote_id,
                ApprovalRequest.quote_version_id != new_version.id,
                ApprovalRequest.status.in_(
                    [ApprovalRequestStatus.APPROVED, ApprovalRequestStatus.PENDING]
                ),
            )
        )
        requests = list(result.scalars())
        now = datetime.now(UTC)
        headline = (
            material_changes[0]["reason"]
            if material_changes
            else "A material change was detected."
        )
        records: list[StaleDecisionRecord] = []

        for request in requests:
            steps = await cls.steps_for_request(session, request.id)

            if request.status is ApprovalRequestStatus.APPROVED:
                # No steps means the policy engine approved it, not a person.
                was_automatic = not steps
                decision_label = (
                    "AUTO_APPROVED" if was_automatic else ApprovalRequestStatus.APPROVED.value
                )
                reason = (
                    f"{'Automatic approval' if was_automatic else 'Approval'} of "
                    f"version "
                    f"{await cls._version_number(session, request.quote_version_id)} is "
                    f"no longer valid: {headline}"
                )
                request.status = ApprovalRequestStatus.STALE
                request.stale_at = now
                request.stale_reason = reason
                for step in steps:
                    if step.status is ApprovalStepStatus.APPROVED:
                        step.status = ApprovalStepStatus.STALE

                decisions = await cls.decisions_for_request(session, request.id)
                last = decisions[-1] if decisions else None
                records.append(
                    StaleDecisionRecord(
                        approval_request_id=request.id,
                        previous_decision=decision_label,
                        reason=reason,
                        decided_at=request.decided_at,
                        decided_by=(
                            last.actor_email
                            if last
                            else ("policy engine" if was_automatic else None)
                        ),
                    )
                )
                await session.flush()
                await AuditService.emit(
                    session,
                    EventType.APPROVAL_MARKED_STALE,
                    organization_id=request.organization_id,
                    entity_type="approval_request",
                    entity_id=request.id,
                    actor=actor,
                    payload={
                        "quote_id": str(quote_id),
                        "stale_version_id": str(request.quote_version_id),
                        "new_version_id": str(new_version.id),
                        "new_version_number": new_version.version_number,
                        "previous_decision": decision_label,
                        "reason": reason,
                        "material_changes": jsonable(list(material_changes)),
                    },
                )
            else:
                request.status = ApprovalRequestStatus.CANCELLED
                request.stale_reason = (
                    f"Superseded by version {new_version.version_number} before a "
                    f"decision was made: {headline}"
                )
                for step in steps:
                    if step.status is ApprovalStepStatus.PENDING:
                        step.status = ApprovalStepStatus.SKIPPED
                await session.flush()

            await AttentionService.resolve(
                session,
                organization_id=request.organization_id,
                source_type="approval_request",
                source_id=request.id,
                item_type=AttentionItemType.PENDING_APPROVAL,
                note=f"Superseded by version {new_version.version_number}.",
                actor=actor,
            )

        return records

    @staticmethod
    async def _version_number(session: AsyncSession, version_id: uuid.UUID) -> int:
        version = await session.get(QuoteVersion, version_id)
        return version.version_number if version else 0

    # -------------------------------------------------------------- inbox
    @classmethod
    async def inbox(cls, session: AsyncSession, user: User) -> list[dict[str, Any]]:
        """Steps this user can actually act on, right now."""
        stmt = (
            select(ApprovalStep, ApprovalRequest, QuoteVersion, Quote)
            .join(ApprovalRequest, ApprovalStep.approval_request_id == ApprovalRequest.id)
            .join(QuoteVersion, ApprovalRequest.quote_version_id == QuoteVersion.id)
            .join(Quote, ApprovalRequest.quote_id == Quote.id)
            .where(
                ApprovalRequest.organization_id == user.organization_id,
                ApprovalRequest.status == ApprovalRequestStatus.PENDING,
                ApprovalStep.status == ApprovalStepStatus.PENDING,
                ApprovalStep.sequence == ApprovalRequest.current_step_sequence,
            )
            .order_by(ApprovalRequest.created_at)
        )
        if user.role_code is not RoleCode.ADMIN:
            stmt = stmt.where(ApprovalStep.required_role == user.role_code)

        rows = (await session.execute(stmt)).all()
        items: list[dict[str, Any]] = []
        for step, request, version, quote in rows:
            # Self-approval is impossible, so it does not belong in a to-do list.
            if cls._is_self_approval(user, request, version, quote):
                continue
            profile = await cls._customer_name(session, quote)
            requester = await session.get(User, request.requested_by_user_id)
            items.append(
                {
                    "approval_request_id": request.id,
                    "approval_step_id": step.id,
                    "quote_id": quote.id,
                    "quote_version_id": version.id,
                    "quote_number": quote.quote_number,
                    "version_number": version.version_number,
                    "title": quote.title,
                    "customer_name": profile,
                    "level": step.level,
                    "sequence": step.sequence,
                    "reason": step.reason,
                    "blended_risk_score": request.blended_risk_score,
                    "total_revenue": version.total_revenue,
                    "margin_pct": version.margin_pct,
                    "requested_by_email": requester.email if requester else "unknown",
                    "is_reapproval": request.reason.startswith("Re-approval"),
                    "waiting_since": request.created_at,
                }
            )
        return items

    @staticmethod
    async def _customer_name(session: AsyncSession, quote: Quote) -> str:
        from app.models.customer_profile import CustomerProfile
        from app.models.deal import Deal

        row = (
            await session.execute(
                select(CustomerProfile.display_name)
                .join(Deal, Deal.customer_profile_id == CustomerProfile.id)
                .where(Deal.id == quote.deal_id)
            )
        ).scalar_one_or_none()
        return row or "Unknown customer"

    @staticmethod
    def _is_self_approval(
        user: User,
        request: ApprovalRequest,
        version: QuoteVersion,
        quote: Quote,
    ) -> bool:
        return user.id in {
            request.requested_by_user_id,
            version.created_by_user_id,
            quote.created_by_user_id,
        }

    # ------------------------------------------------------------ decisions
    @classmethod
    async def decide(
        cls,
        session: AsyncSession,
        *,
        request_id: uuid.UUID,
        actor: User,
        decision: ApprovalDecisionType,
        reason: str,
    ) -> tuple[ApprovalRequest, QuoteVersion, str]:
        request = await session.get(ApprovalRequest, request_id)
        if request is None or request.organization_id != actor.organization_id:
            raise NotFoundError("Approval request not found.")

        version = await session.get(QuoteVersion, request.quote_version_id)
        quote = await session.get(Quote, request.quote_id)
        if version is None or quote is None:
            raise NotFoundError("Approval request is not linked to a live quote.")

        if request.status is not ApprovalRequestStatus.PENDING:
            raise ConflictError(
                f"Approval request is {request.status.value} and can no longer be "
                f"decided.",
                code="APPROVAL_NOT_PENDING",
                details={"status": request.status.value},
            )

        # ---- INVARIANT: nobody approves their own work -------------------
        if cls._is_self_approval(actor, request, version, quote):
            raise AuthorizationError(
                "You cannot decide an approval for a quote you created or submitted.",
                code="SELF_APPROVAL_FORBIDDEN",
                details={
                    "actor_user_id": str(actor.id),
                    "requested_by_user_id": str(request.requested_by_user_id),
                    "version_created_by_user_id": str(version.created_by_user_id),
                },
            )

        steps = await cls.steps_for_request(session, request.id)
        step = next(
            (
                s
                for s in steps
                if s.sequence == request.current_step_sequence
                and s.status is ApprovalStepStatus.PENDING
            ),
            None,
        )
        if step is None:
            decided = [s for s in steps if s.status is not ApprovalStepStatus.PENDING]
            raise ConflictError(
                "There is no pending step to decide on this request.",
                code="NO_PENDING_STEP",
                details={
                    "already_decided": [
                        {"sequence": s.sequence, "status": s.status.value}
                        for s in decided
                    ]
                },
            )

        if (
            actor.role_code is not RoleCode.ADMIN
            and step.required_role != actor.role_code
        ):
            raise AuthorizationError(
                f"Step {step.sequence} requires the "
                f"{step.required_role.value} role; you hold "
                f"{actor.role_code.value}.",
                code="WRONG_APPROVER_ROLE",
                details={
                    "required_role": step.required_role.value,
                    "your_role": actor.role_code.value,
                    "level": step.level.value,
                },
            )

        now = datetime.now(UTC)
        snapshot = {
            "version_number": version.version_number,
            "total_revenue": str(money(version.total_revenue)),
            "net_revenue": str(money(version.net_revenue)),
            "total_cost": str(money(version.total_cost)),
            "margin": str(money(version.margin)),
            "margin_pct": str(pct(version.margin_pct)),
            "total_discount": str(money(version.total_discount)),
            "blended_risk_score": str(pct(version.blended_risk_score)),
            "risk_band": version.risk_band.value,
        }

        session.add(
            ApprovalDecision(
                organization_id=request.organization_id,
                approval_request_id=request.id,
                approval_step_id=step.id,
                quote_version_id=version.id,
                decision=decision,
                actor_user_id=actor.id,
                actor_role=actor.role_code,
                actor_email=actor.email,
                reason=reason,
                decision_snapshot=snapshot,
                decided_at=now,
            )
        )
        step.decided_by_user_id = actor.id
        step.decided_at = now
        step.decision_reason = reason

        if decision is ApprovalDecisionType.APPROVE:
            message = await cls._apply_approve(
                session,
                request=request,
                step=step,
                steps=steps,
                version=version,
                quote=quote,
                actor=actor,
                reason=reason,
                snapshot=snapshot,
                now=now,
            )
        elif decision is ApprovalDecisionType.REJECT:
            message = await cls._apply_reject(
                session,
                request=request,
                step=step,
                steps=steps,
                version=version,
                quote=quote,
                actor=actor,
                reason=reason,
                snapshot=snapshot,
                now=now,
            )
        else:
            message = await cls._apply_request_revision(
                session,
                request=request,
                step=step,
                steps=steps,
                version=version,
                quote=quote,
                actor=actor,
                reason=reason,
                snapshot=snapshot,
                now=now,
            )

        await session.flush()
        return request, version, message

    @classmethod
    async def _apply_approve(
        cls,
        session: AsyncSession,
        *,
        request: ApprovalRequest,
        step: ApprovalStep,
        steps: Sequence[ApprovalStep],
        version: QuoteVersion,
        quote: Quote,
        actor: User,
        reason: str,
        snapshot: dict[str, Any],
        now: datetime,
    ) -> str:
        step.status = ApprovalStepStatus.APPROVED
        await session.flush()

        await AuditService.emit(
            session,
            EventType.APPROVAL_GRANTED,
            organization_id=request.organization_id,
            entity_type="approval_request",
            entity_id=request.id,
            actor=actor,
            payload={
                "quote_version_id": str(version.id),
                "version_number": version.version_number,
                "step_sequence": step.sequence,
                "level": step.level.value,
                "reason": reason,
                "financials_at_decision": snapshot,
            },
        )

        remaining = [
            s
            for s in steps
            if s.sequence > step.sequence and s.status is ApprovalStepStatus.PENDING
        ]
        if remaining:
            next_step = min(remaining, key=lambda s: s.sequence)
            request.current_step_sequence = next_step.sequence
            await session.flush()
            await AttentionService.upsert(
                session,
                organization_id=request.organization_id,
                source_type="approval_request",
                source_id=request.id,
                item_type=AttentionItemType.PENDING_APPROVAL,
                severity=Severity.MEDIUM,
                title=(
                    f"{_level_label(next_step.level)} approval needed on "
                    f"{quote.quote_number} v{version.version_number}"
                ),
                reason=next_step.reason,
                impact=(
                    f"{_level_label(step.level)} has approved; the quote still "
                    f"cannot be sent until {_level_label(next_step.level)} signs off."
                ),
                owner_role=next_step.required_role,
                recommended_action=(
                    "Review the policy findings and approve, reject or request a "
                    "revision."
                ),
                deal_id=quote.deal_id,
                quote_id=quote.id,
                detail={
                    "quote_version_id": str(version.id),
                    "level": next_step.level.value,
                },
                actor=actor,
            )
            return (
                f"{_level_label(step.level)} approved. Now awaiting "
                f"{_level_label(next_step.level)} approval."
            )

        # -------------------------------------------- fully approved
        request.status = ApprovalRequestStatus.APPROVED
        request.decided_at = now
        version.status = QuoteVersionStatus.APPROVED
        version.approved_at = now
        version.is_stale = False
        version.stale_reason = None
        await session.flush()

        await AuditService.emit(
            session,
            EventType.QUOTE_APPROVED,
            organization_id=request.organization_id,
            entity_type="quote_version",
            entity_id=version.id,
            actor=actor,
            payload={
                "quote_id": str(quote.id),
                "version_number": version.version_number,
                "approval_request_id": str(request.id),
                "levels": [s.level.value for s in steps],
                "financials_at_decision": snapshot,
            },
        )

        await AttentionService.resolve(
            session,
            organization_id=request.organization_id,
            source_type="approval_request",
            source_id=request.id,
            item_type=AttentionItemType.PENDING_APPROVAL,
            note="All required approvals granted.",
            actor=actor,
        )
        # A fresh approval clears every stale-approval alert on this quote.
        for record in await cls.stale_records_for_quote(session, quote.id):
            await AttentionService.resolve(
                session,
                organization_id=request.organization_id,
                source_type="approval_request",
                source_id=record.approval_request_id,
                item_type=AttentionItemType.STALE_APPROVAL,
                note=(
                    f"Version {version.version_number} has been approved, replacing "
                    f"the invalidated decision."
                ),
                actor=actor,
            )
        await AttentionService.resolve(
            session,
            organization_id=request.organization_id,
            source_type="quote",
            source_id=quote.id,
            item_type=AttentionItemType.ORDER_BLOCKED,
            note="Approval renewed; the order is no longer blocked.",
            actor=actor,
        )
        return "Quote fully approved and ready to send."

    @classmethod
    async def _apply_reject(
        cls,
        session: AsyncSession,
        *,
        request: ApprovalRequest,
        step: ApprovalStep,
        steps: Sequence[ApprovalStep],
        version: QuoteVersion,
        quote: Quote,
        actor: User,
        reason: str,
        snapshot: dict[str, Any],
        now: datetime,
    ) -> str:
        step.status = ApprovalStepStatus.REJECTED
        for other in steps:
            if other.status is ApprovalStepStatus.PENDING and other.id != step.id:
                other.status = ApprovalStepStatus.SKIPPED
        request.status = ApprovalRequestStatus.REJECTED
        request.decided_at = now
        version.status = QuoteVersionStatus.REJECTED
        version.rejected_at = now
        await session.flush()

        await AuditService.emit(
            session,
            EventType.APPROVAL_REJECTED,
            organization_id=request.organization_id,
            entity_type="approval_request",
            entity_id=request.id,
            actor=actor,
            payload={
                "quote_version_id": str(version.id),
                "version_number": version.version_number,
                "step_sequence": step.sequence,
                "level": step.level.value,
                "reason": reason,
                "financials_at_decision": snapshot,
            },
        )
        await AttentionService.resolve(
            session,
            organization_id=request.organization_id,
            source_type="approval_request",
            source_id=request.id,
            item_type=AttentionItemType.PENDING_APPROVAL,
            note=f"Rejected by {actor.email}.",
            actor=actor,
        )
        return (
            f"Quote version {version.version_number} rejected. It is now immutable; "
            f"create a new quote version to continue."
        )

    @classmethod
    async def _apply_request_revision(
        cls,
        session: AsyncSession,
        *,
        request: ApprovalRequest,
        step: ApprovalStep,
        steps: Sequence[ApprovalStep],
        version: QuoteVersion,
        quote: Quote,
        actor: User,
        reason: str,
        snapshot: dict[str, Any],
        now: datetime,
    ) -> str:
        """Return the version to the sales rep for edits.

        The version never reached ``APPROVED``, so no decision is being
        rewritten: it simply goes back to ``DRAFT`` and becomes editable again.
        """
        step.status = ApprovalStepStatus.REVISION_REQUESTED
        for other in steps:
            if other.status is ApprovalStepStatus.PENDING and other.id != step.id:
                other.status = ApprovalStepStatus.SKIPPED
        request.status = ApprovalRequestStatus.REVISION_REQUESTED
        request.decided_at = now
        version.status = QuoteVersionStatus.DRAFT
        version.submitted_at = None
        await session.flush()

        await AuditService.emit(
            session,
            EventType.APPROVAL_REVISION_REQUESTED,
            organization_id=request.organization_id,
            entity_type="approval_request",
            entity_id=request.id,
            actor=actor,
            payload={
                "quote_version_id": str(version.id),
                "version_number": version.version_number,
                "level": step.level.value,
                "reason": reason,
                "financials_at_decision": snapshot,
            },
        )
        await AttentionService.resolve(
            session,
            organization_id=request.organization_id,
            source_type="approval_request",
            source_id=request.id,
            item_type=AttentionItemType.PENDING_APPROVAL,
            note=f"Revision requested by {actor.email}.",
            actor=actor,
        )
        await AttentionService.upsert(
            session,
            organization_id=request.organization_id,
            source_type="quote_version",
            source_id=version.id,
            item_type=AttentionItemType.CUSTOMER_RESPONSE_REQUIRED,
            severity=Severity.MEDIUM,
            title=(
                f"Revision requested on {quote.quote_number} "
                f"v{version.version_number}"
            ),
            reason=f"{_level_label(step.level)} asked for changes: {reason}",
            impact="The quote is back in draft and cannot be sent until resubmitted.",
            owner_role=RoleCode.SALES,
            owner_user_id=version.created_by_user_id,
            recommended_action="Amend the quote lines and submit for approval again.",
            deal_id=quote.deal_id,
            quote_id=quote.id,
            detail={"requested_by": actor.email},
            actor=actor,
        )
        return (
            f"Revision requested. Version {version.version_number} is back in DRAFT "
            f"and editable."
        )

    # ------------------------------------------------- confirmation gate
    @classmethod
    async def assert_confirmable(
        cls, session: AsyncSession, version: QuoteVersion
    ) -> None:
        """Raise unless this version may become an order.

        Enforced server-side on the portal confirm endpoint. This is the single
        chokepoint that stops an order being created on a decision that no
        longer holds.
        """
        from app.errors import ApprovalRequiredError, StaleApprovalError

        if version.status is QuoteVersionStatus.CONFIRMED:
            raise ConflictError(
                "This quote version has already been confirmed.",
                code="ALREADY_CONFIRMED",
            )
        if version.status in (
            QuoteVersionStatus.REJECTED,
            QuoteVersionStatus.SUPERSEDED,
        ):
            raise ConflictError(
                f"Version is {version.status.value} and can never be confirmed.",
                code="VERSION_NOT_CONFIRMABLE",
                details={"status": version.status.value},
            )

        if version.is_stale:
            raise StaleApprovalError(
                version.stale_reason
                or (
                    "A material change invalidated the approval for this quote. "
                    "It must be re-approved before it can be confirmed."
                ),
                details={
                    "quote_version_id": str(version.id),
                    "version_number": version.version_number,
                },
            )

        if version.requires_approval:
            request = await cls.latest_request_for_version(session, version.id)
            if request is None:
                raise ApprovalRequiredError(
                    "This quote requires approval but no approval request exists.",
                    details={"version_number": version.version_number},
                )
            if request.status is ApprovalRequestStatus.STALE:
                raise StaleApprovalError(
                    request.stale_reason or "The approval for this quote is stale.",
                    details={"approval_request_id": str(request.id)},
                )
            if request.status is ApprovalRequestStatus.PENDING:
                steps = await cls.steps_for_request(session, request.id)
                pending = [
                    s.level.value
                    for s in steps
                    if s.status is ApprovalStepStatus.PENDING
                ]
                raise ApprovalRequiredError(
                    "This quote is still awaiting approval and cannot be confirmed.",
                    details={
                        "approval_request_id": str(request.id),
                        "awaiting": pending,
                    },
                )
            if request.status is not ApprovalRequestStatus.APPROVED:
                raise ApprovalRequiredError(
                    f"The approval for this quote is {request.status.value}.",
                    details={"approval_request_id": str(request.id)},
                )

        if version.status not in (
            QuoteVersionStatus.APPROVED,
            QuoteVersionStatus.SENT,
            QuoteVersionStatus.NEGOTIATING,
        ):
            raise BusinessRuleError(
                f"A {version.status.value} quote version cannot be confirmed. It must "
                f"be approved and sent to the customer first.",
                code="VERSION_NOT_SENT",
                details={"status": version.status.value},
            )

    @staticmethod
    def blocked_reason(version: QuoteVersion, request: ApprovalRequest | None) -> str | None:
        """Customer-safe explanation of why confirmation is unavailable.

        Deliberately vague about *internal* reasoning: the customer learns that
        the seller is still reviewing, not what the margin or policy said.
        """
        if version.status is QuoteVersionStatus.CONFIRMED:
            return "This quote has already been confirmed."
        if version.status in (
            QuoteVersionStatus.REJECTED,
            QuoteVersionStatus.SUPERSEDED,
        ):
            return "This version is no longer current."
        if version.is_stale:
            return (
                "Your requested changes are being reviewed by our team. You will be "
                "able to confirm once the updated quote is approved."
            )
        if version.requires_approval and (
            request is None or request.status is not ApprovalRequestStatus.APPROVED
        ):
            return "This quote is pending internal review."
        if version.status not in (
            QuoteVersionStatus.SENT,
            QuoteVersionStatus.NEGOTIATING,
            QuoteVersionStatus.APPROVED,
        ):
            return "This quote has not been issued yet."
        return None
