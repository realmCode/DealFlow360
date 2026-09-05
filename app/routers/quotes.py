"""Quote, version and line endpoints.

Line mutation is restricted to ``DRAFT`` versions at the router boundary *and*
in :class:`QuoteService`, so an alternate call path cannot bypass the rule.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import func, select

from app.dependencies import DbSession, InternalUser, SalesUser
from app.enums import (
    DealStage,
    QuoteStatus,
    QuoteVersionSource,
    QuoteVersionStatus,
    RiskBand,
)
from app.errors import NotFoundError
from app.models.customer_profile import CustomerProfile
from app.models.deal import Deal
from app.models.dismissed_recommendation import DismissedRecommendation
from app.models.quote import Quote
from app.models.quote_line import QuoteLine
from app.models.quote_version import QuoteVersion
from app.models.user import User
from app.schemas.common import Page
from app.schemas.decision_fabric import DecisionFabricResult
from app.schemas.policy import PolicyEvaluationRead, PolicyResultRead
from app.schemas.query import Pagination, Sorting
from app.schemas.simulation import SimulationRequest, SimulationResult
from app.schemas.quote import (
    OrderDiscountUpdate,
    QuoteLineCreate,
    QuoteLineRead,
    QuoteLineUpdate,
    QuoteListItem,
    QuoteLoseRequest,
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
from app.services.settings_service import SettingsService
from app.services.simulation_service import SimulationService

router = APIRouter(tags=["quotes"])

#: Sortable columns for GET /quotes. An allowlist, because the value reaches
#: an ORDER BY clause.
QUOTE_SORTABLE = {
    "created_at": Quote.created_at,
    "updated_at": Quote.updated_at,
    "quote_number": Quote.quote_number,
    "title": Quote.title,
    "status": Quote.status,
}


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


# --------------------------------------------------------------------- lists
@router.get(
    "/quotes",
    response_model=Page[QuoteListItem],
    summary="List quotations for the workspace list and Kanban pipeline",
)
async def list_quotes(
    user: InternalUser,
    db: DbSession,
    page: Pagination,
    sort: Sorting,
    status_: QuoteStatus | None = Query(default=None, alias="status"),
    version_status: QuoteVersionStatus | None = Query(default=None),
    deal_stage: DealStage | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None),
    customer_profile_id: uuid.UUID | None = Query(default=None),
    risk_band: RiskBand | None = Query(default=None),
    is_stale: bool | None = Query(default=None),
    requires_approval: bool | None = Query(default=None),
    q: str | None = Query(
        default=None,
        max_length=128,
        description="Search quote number, title or customer name.",
    ),
) -> Page[QuoteListItem]:
    """PDF B1/B2.

    One query returns everything the cards need — "customer, amount, and
    stage" — instead of forcing the client to walk /deals and then fetch each
    quote. The current version is joined on ``version_number`` because
    ``quotes.current_version_number`` is an integer rather than a foreign key
    (deliberately, to avoid a circular FK between the two tables).
    """
    # Every column is explicitly labelled: selecting whole entities alongside
    # an alias of the same table produces colliding keys in the result mapping.
    cv = QuoteVersion.__table__.alias("cv")

    line_count = (
        select(func.count())
        .select_from(QuoteLine)
        .where(QuoteLine.quote_version_id == cv.c.id)
        .correlate(cv)
        .scalar_subquery()
    )
    version_count = (
        select(func.count())
        .select_from(QuoteVersion)
        .where(QuoteVersion.quote_id == Quote.id)
        .correlate(Quote)
        .scalar_subquery()
    )

    stmt = (
        select(
            Quote.id.label("quote_id"),
            Quote.quote_number.label("quote_number"),
            Quote.title.label("title"),
            Quote.status.label("quote_status"),
            Quote.deal_id.label("deal_id"),
            Quote.current_version_number.label("current_version_number"),
            Quote.created_at.label("quote_created_at"),
            Quote.updated_at.label("quote_updated_at"),
            Deal.reference.label("deal_reference"),
            Deal.stage.label("deal_stage"),
            Deal.owner_user_id.label("owner_user_id"),
            CustomerProfile.id.label("profile_id"),
            CustomerProfile.display_name.label("customer_display_name"),
            CustomerProfile.tier.label("customer_tier"),
            User.full_name.label("owner_name"),
            cv.c.id.label("version_id"),
            cv.c.status.label("version_status"),
            cv.c.total_revenue.label("total_revenue"),
            cv.c.net_revenue.label("net_revenue"),
            cv.c.margin_pct.label("margin_pct"),
            cv.c.effective_discount_pct.label("effective_discount_pct"),
            cv.c.blended_risk_score.label("blended_risk_score"),
            cv.c.risk_band.label("risk_band"),
            cv.c.requires_approval.label("requires_approval"),
            cv.c.is_stale.label("is_stale"),
            cv.c.updated_at.label("version_updated_at"),
            line_count.label("line_count"),
            version_count.label("version_count"),
        )
        .select_from(Quote)
        .join(Deal, Deal.id == Quote.deal_id)
        .join(CustomerProfile, CustomerProfile.id == Deal.customer_profile_id)
        .outerjoin(User, User.id == Deal.owner_user_id)
        .outerjoin(
            cv,
            (cv.c.quote_id == Quote.id)
            & (cv.c.version_number == Quote.current_version_number),
        )
        .where(Quote.organization_id == user.organization_id)
    )

    if status_ is not None:
        stmt = stmt.where(Quote.status == status_)
    if version_status is not None:
        stmt = stmt.where(cv.c.status == version_status)
    if deal_stage is not None:
        stmt = stmt.where(Deal.stage == deal_stage)
    if owner_user_id is not None:
        stmt = stmt.where(Deal.owner_user_id == owner_user_id)
    if customer_profile_id is not None:
        stmt = stmt.where(Deal.customer_profile_id == customer_profile_id)
    if risk_band is not None:
        stmt = stmt.where(cv.c.risk_band == risk_band)
    if is_stale is not None:
        stmt = stmt.where(cv.c.is_stale.is_(is_stale))
    if requires_approval is not None:
        stmt = stmt.where(cv.c.requires_approval.is_(requires_approval))
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            Quote.quote_number.ilike(needle)
            | Quote.title.ilike(needle)
            | CustomerProfile.display_name.ilike(needle)
        )

    total = (
        await db.execute(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
    ).scalar_one()

    column, descending = sort.resolve(QUOTE_SORTABLE, default="created_at")
    stmt = stmt.order_by(column.desc() if descending else column.asc())
    stmt = stmt.limit(page.limit).offset(page.offset)

    now = datetime.now(UTC)
    items: list[QuoteListItem] = []
    for row in (await db.execute(stmt)).mappings():
        created = row["quote_created_at"]
        items.append(
            QuoteListItem(
                quote_id=row["quote_id"],
                quote_number=row["quote_number"],
                title=row["title"],
                status=row["quote_status"],
                deal_id=row["deal_id"],
                deal_reference=row["deal_reference"],
                deal_stage=row["deal_stage"].value,
                customer_profile_id=row["profile_id"],
                customer_display_name=row["customer_display_name"],
                customer_tier=(
                    row["customer_tier"].value if row["customer_tier"] else None
                ),
                current_version_id=row["version_id"],
                current_version_number=row["current_version_number"],
                current_version_status=row["version_status"],
                total_revenue=row["total_revenue"] or 0,
                net_revenue=row["net_revenue"] or 0,
                margin_pct=row["margin_pct"] or 0,
                effective_discount_pct=row["effective_discount_pct"] or 0,
                blended_risk_score=row["blended_risk_score"] or 0,
                risk_band=row["risk_band"],
                requires_approval=bool(row["requires_approval"]),
                is_stale=bool(row["is_stale"]),
                owner_user_id=row["owner_user_id"],
                owner_name=row["owner_name"],
                line_count=int(row["line_count"] or 0),
                version_count=int(row["version_count"] or 0),
                age_days=max(0, (now - created).days),
                last_activity_at=row["version_updated_at"] or row["quote_updated_at"],
                created_at=created,
            )
        )

    return Page[QuoteListItem](
        items=items, total=int(total), limit=page.limit, offset=page.offset
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


@router.patch(
    "/quote-versions/{version_id}/discount",
    response_model=QuoteVersionRead,
    summary="Set the order-level discount on a DRAFT version",
)
async def set_order_discount(
    version_id: uuid.UUID,
    payload: OrderDiscountUpdate,
    user: SalesUser,
    db: DbSession,
) -> QuoteVersionRead:
    """PDF B3 — "Apply line level or order level discounts".

    Recalculating here matters: the order discount compounds with each line's
    own discount, and the compounded figure is what policy ceilings are judged
    against, so the risk picture has to be refreshed immediately.
    """
    version = await QuoteService.get_version(db, version_id, user.organization_id)
    QuoteService.assert_editable(version)
    version.order_discount_pct = payload.order_discount_pct
    await QuoteService.recalculate(db, version)
    await db.commit()
    return await _version_read(db, version)


@router.post(
    "/quotes/{quote_id}/lose",
    response_model=QuoteRead,
    summary="Mark a quote lost and close the deal",
)
async def lose_quote(
    quote_id: uuid.UUID,
    payload: QuoteLoseRequest,
    user: SalesUser,
    db: DbSession,
) -> QuoteRead:
    """Without this, ``QuoteStatus.LOST`` and ``DealStage.CLOSED_LOST`` were
    unreachable, so the pipeline had no way to represent a dead deal and win
    rate could never be computed."""
    quote = await QuoteService.lose(db, quote_id=quote_id, actor=user, reason=payload.reason)
    await db.commit()
    return await _quote_read(db, quote)


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

    # Pass the tenant's own weights, otherwise this read would report a
    # different score from the one persisted at submit time.
    org_settings = await SettingsService.for_org(db, version.organization_id)
    evaluation = PolicyEngine.evaluate(
        version=version,
        lines=lines,
        profile=profile,
        policies=policies,
        weights={
            "overage": Decimal(org_settings.risk_discount_overage_weight),
            "breadth": Decimal(org_settings.risk_breadth_weight),
            "margin": Decimal(org_settings.risk_margin_weight),
            "depth": Decimal(org_settings.risk_depth_weight),
        },
        escalation_threshold=Decimal(org_settings.finance_escalation_threshold),
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
        order_discount_pct=payload.order_discount_pct,
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


@router.post(
    "/quotes/{quote_id}/recommendations/{product_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dismiss a recommendation so it stops reappearing (PDF B5)",
)
async def dismiss_recommendation(
    quote_id: uuid.UUID,
    product_id: uuid.UUID,
    user: SalesUser,
    db: DbSession,
) -> Response:
    """Scoped to the current version, not the quote.

    A revision is a fresh commercial proposal, so a suggestion declined
    against v1's numbers is worth offering again on v2 when they change.
    """
    quote = await QuoteService.get_quote(db, quote_id, user.organization_id)
    version = await QuoteService.current_version(db, quote)
    if version is None:
        raise NotFoundError("This quote has no version to dismiss against.")

    existing = (
        await db.execute(
            select(DismissedRecommendation).where(
                DismissedRecommendation.quote_version_id == version.id,
                DismissedRecommendation.product_id == product_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            DismissedRecommendation(
                organization_id=user.organization_id,
                quote_version_id=version.id,
                product_id=product_id,
                dismissed_by_user_id=user.id,
            )
        )
        await db.flush()
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/quote-versions/{version_id}/simulate",
    response_model=SimulationResult,
    summary="What-if: score a hypothetical discount without persisting anything",
)
async def simulate(
    version_id: uuid.UUID,
    payload: SimulationRequest,
    user: InternalUser,
    db: DbSession,
) -> SimulationResult:
    """Answer "what would this cost me in approvals?" before committing.

    Both `CommercialEngine.calculate_line` and `PolicyEngine.evaluate` are
    already pure functions of their inputs, so this clones the loaded lines in
    memory, applies the hypothetical changes and calls them. Nothing is
    written: no version, no snapshot, no policy result, no audit event.

    Without this a rep can only discover the approval consequence of a
    discount by submitting it, which drags an approver into every experiment.
    """
    version = await QuoteService.get_version(db, version_id, user.organization_id)
    return SimulationResult.model_validate(
        await SimulationService.simulate(
            db,
            version=version,
            line_discounts=payload.line_discounts,
            line_quantities=payload.line_quantities,
            order_discount_pct=payload.order_discount_pct,
            payment_terms=payload.payment_terms,
        )
    )


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
