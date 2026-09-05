"""Approval workflow endpoints.

Only ``MANAGER``, ``FINANCE`` and ``ADMIN`` reach these routes at all, and the
service layer additionally rejects self-approval and wrong-role steps. A SALES
user receives 403 from the dependency before any handler code runs.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.dependencies import ApproverUser, DbSession, InternalUser
from app.enums import ApprovalDecisionType
from app.errors import NotFoundError
from app.models.approval_request import ApprovalRequest
from app.models.customer_profile import CustomerProfile
from app.models.deal import Deal
from app.models.quote import Quote
from app.models.quote_version import QuoteVersion
from app.models.user import User
from app.schemas.approval import (
    ApprovalActionRequest,
    ApprovalActionResponse,
    ApprovalDecisionRead,
    ApprovalInboxItem,
    ApprovalRequestRead,
    ApprovalStepRead,
)
from app.services.approval_service import ApprovalService
from app.services.commercial_engine import money, pct

router = APIRouter(prefix="/approvals", tags=["approvals"])


async def _to_read(db, request: ApprovalRequest) -> ApprovalRequestRead:  # noqa: ANN001
    steps = await ApprovalService.steps_for_request(db, request.id)
    decisions = await ApprovalService.decisions_for_request(db, request.id)
    version = await db.get(QuoteVersion, request.quote_version_id)
    quote = await db.get(Quote, request.quote_id)
    requester = await db.get(User, request.requested_by_user_id)

    customer_name = None
    if quote is not None:
        deal = await db.get(Deal, quote.deal_id)
        if deal is not None:
            profile = await db.get(CustomerProfile, deal.customer_profile_id)
            customer_name = profile.display_name if profile else None

    step_reads: list[ApprovalStepRead] = []
    for step in steps:
        decider = (
            await db.get(User, step.decided_by_user_id)
            if step.decided_by_user_id
            else None
        )
        step_reads.append(
            ApprovalStepRead(
                id=step.id,
                sequence=step.sequence,
                level=step.level,
                required_role=step.required_role,
                status=step.status,
                reason=step.reason,
                assigned_user_id=step.assigned_user_id,
                decided_by_user_id=step.decided_by_user_id,
                decided_by_email=decider.email if decider else None,
                decision_reason=step.decision_reason,
                decided_at=step.decided_at,
            )
        )

    financials = None
    if version is not None:
        financials = {
            "version_number": version.version_number,
            "gross_revenue": str(money(version.gross_revenue)),
            "total_discount": str(money(version.total_discount)),
            "net_revenue": str(money(version.net_revenue)),
            "tax_amount": str(money(version.tax_amount)),
            "total_revenue": str(money(version.total_revenue)),
            "total_cost": str(money(version.total_cost)),
            "margin": str(money(version.margin)),
            "margin_pct": str(pct(version.margin_pct)),
            "effective_discount_pct": str(pct(version.effective_discount_pct)),
            "blended_risk_score": str(pct(version.blended_risk_score)),
            "risk_band": version.risk_band.value,
        }

    return ApprovalRequestRead(
        id=request.id,
        created_at=request.created_at,
        updated_at=request.updated_at,
        quote_id=request.quote_id,
        quote_version_id=request.quote_version_id,
        quote_number=quote.quote_number if quote else None,
        version_number=version.version_number if version else None,
        customer_name=customer_name,
        status=request.status,
        requested_by_user_id=request.requested_by_user_id,
        requested_by_email=requester.email if requester else None,
        reason=request.reason,
        required_levels=request.required_levels,
        policy_summary=request.policy_summary,
        blended_risk_score=request.blended_risk_score,
        current_step_sequence=request.current_step_sequence,
        decided_at=request.decided_at,
        stale_at=request.stale_at,
        stale_reason=request.stale_reason,
        steps=step_reads,
        decisions=[
            ApprovalDecisionRead(
                id=d.id,
                approval_step_id=d.approval_step_id,
                decision=d.decision,
                actor_user_id=d.actor_user_id,
                actor_role=d.actor_role,
                actor_email=d.actor_email,
                reason=d.reason,
                decided_at=d.decided_at,
                decision_snapshot=d.decision_snapshot,
            )
            for d in decisions
        ],
        financials=financials,
    )


@router.get(
    "/inbox",
    response_model=list[ApprovalInboxItem],
    summary="Approvals awaiting *your* decision",
)
async def inbox(user: ApproverUser, db: DbSession) -> list[ApprovalInboxItem]:
    items = await ApprovalService.inbox(db, user)
    return [ApprovalInboxItem(**item) for item in items]


@router.get(
    "/{request_id}",
    response_model=ApprovalRequestRead,
    summary="Approval request detail, including the numbers under review",
)
async def get_request(
    request_id: uuid.UUID, user: InternalUser, db: DbSession
) -> ApprovalRequestRead:
    request = await db.get(ApprovalRequest, request_id)
    if request is None or request.organization_id != user.organization_id:
        raise NotFoundError("Approval request not found.")
    return await _to_read(db, request)


async def _decide(
    db,  # noqa: ANN001
    request_id: uuid.UUID,
    user: User,
    decision: ApprovalDecisionType,
    reason: str,
) -> ApprovalActionResponse:
    request, version, message = await ApprovalService.decide(
        db, request_id=request_id, actor=user, decision=decision, reason=reason
    )
    await db.commit()
    return ApprovalActionResponse(
        approval_request=await _to_read(db, request),
        quote_version_status=version.status.value,
        message=message,
    )


@router.post(
    "/{request_id}/approve",
    response_model=ApprovalActionResponse,
    summary="Approve the current step",
)
async def approve(
    request_id: uuid.UUID,
    payload: ApprovalActionRequest,
    user: ApproverUser,
    db: DbSession,
) -> ApprovalActionResponse:
    return await _decide(
        db, request_id, user, ApprovalDecisionType.APPROVE, payload.reason
    )


@router.post(
    "/{request_id}/reject",
    response_model=ApprovalActionResponse,
    summary="Reject — the version becomes immutable",
)
async def reject(
    request_id: uuid.UUID,
    payload: ApprovalActionRequest,
    user: ApproverUser,
    db: DbSession,
) -> ApprovalActionResponse:
    return await _decide(
        db, request_id, user, ApprovalDecisionType.REJECT, payload.reason
    )


@router.post(
    "/{request_id}/request-revision",
    response_model=ApprovalActionResponse,
    summary="Send back for changes — the version returns to DRAFT",
)
async def request_revision(
    request_id: uuid.UUID,
    payload: ApprovalActionRequest,
    user: ApproverUser,
    db: DbSession,
) -> ApprovalActionResponse:
    return await _decide(
        db, request_id, user, ApprovalDecisionType.REQUEST_REVISION, payload.reason
    )
