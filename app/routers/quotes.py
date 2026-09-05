"""Quote, version and line endpoints.

Line mutation is restricted to ``DRAFT`` versions at the router boundary *and*
in :class:`QuoteService`, so an alternate call path cannot bypass the rule.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.dependencies import DbSession, InternalUser, SalesUser
from app.enums import QuoteVersionSource
from app.schemas.decision_fabric import DecisionFabricResult
from app.schemas.policy import PolicyEvaluationRead, PolicyResultRead
from app.schemas.quote import (
    QuoteLineCreate,
    QuoteLineRead,
    QuoteLineUpdate,
    QuoteRead,
    QuoteVersionRead,
    QuoteVersionSummary,
    RevisionCreate,
    SendRequest,
    SubmitRequest,
)
from app.services.approval_service import ApprovalService
from app.services.commercial_engine import CommercialEngine
from app.services.decision_fabric import DecisionFabric
from app.services.policy_engine import PolicyEngine
from app.services.quote_service import QuoteService
from app.services.recommendation_engine import RecommendationEngine

router = APIRouter(tags=["quotes"])


async def _version_read(db, version) -> QuoteVersionRead:  # noqa: ANN001
    lines = await CommercialEngine.load_lines(db, version.id)
    return QuoteVersionRead(
        **{
            **{
                c.name: getattr(version, c.name)
                for c in version.__table__.columns
                if c.name != "organization_id"
            },
            "is_editable": version.is_editable,
            "lines": [QuoteLineRead.model_validate(line) for line in lines],
        }
    )


async def _quote_read(db, quote) -> QuoteRead:  # noqa: ANN001
    versions = await QuoteService.versions_for_quote(db, quote.id)
    current = next(
        (v for v in versions if v.version_number == quote.current_version_number), None
    )
    return QuoteRead(
        id=quote.id,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
        quote_number=quote.quote_number,
        title=quote.title,
        deal_id=quote.deal_id,
        status=quote.status,
        current_version_number=quote.current_version_number,
        current_version_id=current.id if current else None,
        versions=[QuoteVersionSummary.model_validate(v) for v in versions],
    )


# --------------------------------------------------------------------- reads
@router.get("/quotes/{quote_id}", response_model=QuoteRead, summary="Get a quote")
async def get_quote(
    quote_id: uuid.UUID, user: InternalUser, db: DbSession
) -> QuoteRead:
    quote = await QuoteService.get_quote(db, quote_id, user.organization_id)
    return await _quote_read(db, quote)


@router.get(
    "/quote-versions/{version_id}",
    response_model=QuoteVersionRead,
    summary="Get a quote version with its lines and authoritative totals",
)
async def get_version(
    version_id: uuid.UUID, user: InternalUser, db: DbSession
) -> QuoteVersionRead:
    version = await QuoteService.get_version(db, version_id, user.organization_id)
    return await _version_read(db, version)


# --------------------------------------------------------------------- lines
@router.post(
    "/quote-versions/{version_id}/lines",
    response_model=QuoteVersionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a line to a DRAFT version",
)
async def add_line(
    version_id: uuid.UUID,
    payload: QuoteLineCreate,
    user: SalesUser,
    db: DbSession,
) -> QuoteVersionRead:
    version = await QuoteService.get_version(db, version_id, user.organization_id)
    await QuoteService.add_line(db, version=version, payload=payload, actor=user)
    await db.commit()
    return await _version_read(db, version)


@router.patch(
    "/quote-versions/{version_id}/lines/{line_id}",
    response_model=QuoteVersionRead,
    summary="Update a line on a DRAFT version",
)
async def update_line(
    version_id: uuid.UUID,
    line_id: uuid.UUID,
    payload: QuoteLineUpdate,
    user: SalesUser,
    db: DbSession,
) -> QuoteVersionRead:
    version = await QuoteService.get_version(db, version_id, user.organization_id)
    QuoteService.assert_editable(version)
    line = await QuoteService.get_line(db, version, line_id)
    await QuoteService.update_line(db, version=version, line=line, payload=payload)
    await db.commit()
    return await _version_read(db, version)


@router.delete(
    "/quote-versions/{version_id}/lines/{line_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a line from a DRAFT version",
)
async def delete_line(
    version_id: uuid.UUID,
    line_id: uuid.UUID,
    user: SalesUser,
    db: DbSession,
) -> Response:
    version = await QuoteService.get_version(db, version_id, user.organization_id)
    QuoteService.assert_editable(version)
    line = await QuoteService.get_line(db, version, line_id)
    await QuoteService.delete_line(db, version=version, line=line)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- calculate
@router.post(
    "/quote-versions/{version_id}/calculate",
    response_model=QuoteVersionRead,
    summary="Recalculate totals, margin and snapshot (backend is authoritative)",
)
async def calculate(
    version_id: uuid.UUID, user: InternalUser, db: DbSession
) -> QuoteVersionRead:
    version = await QuoteService.get_version(db, version_id, user.organization_id)
    await QuoteService.recalculate(db, version)
    await db.commit()
    return await _version_read(db, version)


@router.get(
    "/quote-versions/{version_id}/policy-results",
    response_model=PolicyEvaluationRead,
    summary="Explainable policy evaluation for a version",
)
async def policy_results(
    version_id: uuid.UUID, user: InternalUser, db: DbSession
) -> PolicyEvaluationRead:
    version = await QuoteService.get_version(db, version_id, user.organization_id)
    quote = await QuoteService.get_quote(db, version.quote_id, user.organization_id)
    profile = await QuoteService.profile_for_quote(db, quote)
    lines = await CommercialEngine.load_lines(db, version.id)
    policies = await PolicyEngine.active_policies(db, version.organization_id)

    evaluation = PolicyEngine.evaluate(
        version=version, lines=lines, profile=profile, policies=policies
    )
    stored = await PolicyEngine.stored_results(db, version.id)

    return PolicyEvaluationRead(
        quote_version_id=version.id,
        evaluated_at=evaluation.evaluated_at,
        policy_results=[PolicyResultRead.model_validate(r) for r in stored],
        blended_risk=evaluation.blended_risk.as_dict(),
        required_approvals=[r.as_dict() for r in evaluation.required_approvals],
        requires_approval=evaluation.requires_approval,
        violation_count=len(evaluation.violations),
    )


# ------------------------------------------------------------------- submit
@router.post(
    "/quote-versions/{version_id}/submit",
    response_model=DecisionFabricResult,
    summary="Submit for approval — routing is derived from policy, automatically",
)
async def submit(
    version_id: uuid.UUID,
    payload: SubmitRequest,
    user: SalesUser,
    db: DbSession,
) -> DecisionFabricResult:
    version = await QuoteService.get_version(db, version_id, user.organization_id)
    await QuoteService.submit(db, version=version, actor=user, note=payload.note)
    await db.commit()
    return DecisionFabricResult.model_validate(
        await DecisionFabric.impact_for_version(db, version)
    )


@router.get(
    "/quote-versions/{version_id}/impact",
    response_model=DecisionFabricResult,
    summary="Decision Fabric result: what changed, what it broke, who must act",
)
async def impact(
    version_id: uuid.UUID, user: InternalUser, db: DbSession
) -> DecisionFabricResult:
    version = await QuoteService.get_version(db, version_id, user.organization_id)
    return DecisionFabricResult.model_validate(
        await DecisionFabric.impact_for_version(db, version)
    )


# ----------------------------------------------------------------- revision
@router.post(
    "/quote-versions/{version_id}/revisions",
    response_model=QuoteVersionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create the next version — supersedes this one and re-runs governance",
)
async def create_revision(
    version_id: uuid.UUID,
    payload: RevisionCreate,
    user: SalesUser,
    db: DbSession,
) -> QuoteVersionRead:
    version = await QuoteService.get_version(db, version_id, user.organization_id)
    new_version, _outcome = await QuoteService.create_revision(
        db,
        version=version,
        actor=user,
        reason=payload.reason,
        source=QuoteVersionSource.INTERNAL_REVISION,
        line_updates=payload.line_updates,
        add_lines=payload.add_lines,
        remove_line_ids=payload.remove_line_ids,
        payment_terms=payload.payment_terms,
        submit=True,
    )
    await db.commit()
    return await _version_read(db, new_version)


@router.post(
    "/quote-versions/{version_id}/send",
    response_model=QuoteVersionRead,
    summary="Send an APPROVED version to the customer portal",
)
async def send(
    version_id: uuid.UUID,
    payload: SendRequest,
    user: SalesUser,
    db: DbSession,
) -> QuoteVersionRead:
    version = await QuoteService.get_version(db, version_id, user.organization_id)
    await QuoteService.send(db, version=version, actor=user, note=payload.note)
    await db.commit()
    return await _version_read(db, version)


# ------------------------------------------------------------------- P1
@router.get(
    "/quotes/{quote_id}/recommendations",
    summary="Upsell / cross-sell recommendations (P1)",
)
async def recommendations(
    quote_id: uuid.UUID, user: InternalUser, db: DbSession
) -> dict[str, object]:
    quote = await QuoteService.get_quote(db, quote_id, user.organization_id)
    version = await QuoteService.current_version(db, quote)
    if version is None:
        return {"quote_id": str(quote_id), "recommendations": []}
    return {
        "quote_id": str(quote_id),
        "quote_version_id": str(version.id),
        "recommendations": await RecommendationEngine.for_version(db, version),
    }


@router.get(
    "/quote-versions/{version_id}/approval",
    summary="The approval request covering this version",
)
async def version_approval(
    version_id: uuid.UUID, user: InternalUser, db: DbSession
) -> dict[str, object]:
    version = await QuoteService.get_version(db, version_id, user.organization_id)
    request = await ApprovalService.latest_request_for_version(db, version.id)
    if request is None:
        return {
            "quote_version_id": str(version.id),
            "requires_approval": version.requires_approval,
            "approval_request": None,
        }
    steps = await ApprovalService.steps_for_request(db, request.id)
    return {
        "quote_version_id": str(version.id),
        "requires_approval": version.requires_approval,
        "approval_request": {
            "id": str(request.id),
            "status": request.status.value,
            "reason": request.reason,
            "current_step_sequence": request.current_step_sequence,
            "stale_reason": request.stale_reason,
            "steps": [
                {
                    "sequence": s.sequence,
                    "level": s.level.value,
                    "required_role": s.required_role.value,
                    "status": s.status.value,
                }
                for s in steps
            ],
        },
    }
