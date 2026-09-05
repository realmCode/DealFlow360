"""Deal endpoints, including quote creation."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import func, select

from app.dependencies import DbSession, InternalUser, SalesUser
from app.errors import NotFoundError
from app.models.customer_profile import CustomerProfile
from app.models.deal import Deal
from app.models.quote import Quote
from app.schemas.deal import DealCreate, DealQuoteSummary, DealRead, DealUpdate
from app.schemas.quote import QuoteCreate, QuoteRead, QuoteVersionSummary
from app.services.quote_service import QuoteService

router = APIRouter(tags=["deals"])


async def _to_read(db, deal: Deal) -> DealRead:  # noqa: ANN001
    profile = await db.get(CustomerProfile, deal.customer_profile_id)
    quotes = (
        await db.execute(
            select(Quote).where(Quote.deal_id == deal.id).order_by(Quote.created_at)
        )
    ).scalars()
    return DealRead(
        id=deal.id,
        created_at=deal.created_at,
        updated_at=deal.updated_at,
        reference=deal.reference,
        name=deal.name,
        customer_profile_id=deal.customer_profile_id,
        customer_display_name=profile.display_name if profile else None,
        customer_tier=profile.tier if profile else None,
        owner_user_id=deal.owner_user_id,
        primary_contact_id=deal.primary_contact_id,
        stage=deal.stage,
        currency=deal.currency,
        expected_value=deal.expected_value,
        expected_close_date=deal.expected_close_date,
        notes=deal.notes,
        quotes=[
            DealQuoteSummary(
                id=q.id,
                quote_number=q.quote_number,
                title=q.title,
                status=q.status.value,
                current_version_number=q.current_version_number,
            )
            for q in quotes
        ],
    )


@router.post(
    "/deals",
    response_model=DealRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a deal",
)
async def create_deal(payload: DealCreate, user: SalesUser, db: DbSession) -> DealRead:
    profile = await db.get(CustomerProfile, payload.customer_profile_id)
    if profile is None or profile.organization_id != user.organization_id:
        raise NotFoundError("Customer profile not found.")

    reference = payload.reference
    if not reference:
        count = (
            await db.execute(
                select(func.count())
                .select_from(Deal)
                .where(Deal.organization_id == user.organization_id)
            )
        ).scalar_one()
        reference = f"D-{int(count) + 1:05d}"

    deal = Deal(
        organization_id=user.organization_id,
        reference=reference,
        name=payload.name,
        customer_profile_id=profile.id,
        owner_user_id=user.id,
        primary_contact_id=payload.primary_contact_id,
        stage=payload.stage,
        currency=profile.currency,
        expected_value=payload.expected_value,
        expected_close_date=payload.expected_close_date,
        notes=payload.notes,
    )
    db.add(deal)
    await db.flush()
    await db.commit()
    return await _to_read(db, deal)


@router.get("/deals", response_model=list[DealRead], summary="List deals")
async def list_deals(user: InternalUser, db: DbSession) -> list[DealRead]:
    deals = (
        await db.execute(
            select(Deal)
            .where(Deal.organization_id == user.organization_id)
            .order_by(Deal.created_at.desc())
        )
    ).scalars()
    return [await _to_read(db, d) for d in deals]


@router.get("/deals/{deal_id}", response_model=DealRead, summary="Get one deal")
async def get_deal(deal_id: uuid.UUID, user: InternalUser, db: DbSession) -> DealRead:
    deal = await db.get(Deal, deal_id)
    if deal is None or deal.organization_id != user.organization_id:
        raise NotFoundError("Deal not found.")
    return await _to_read(db, deal)


@router.patch("/deals/{deal_id}", response_model=DealRead, summary="Update a deal")
async def update_deal(
    deal_id: uuid.UUID, payload: DealUpdate, user: SalesUser, db: DbSession
) -> DealRead:
    deal = await db.get(Deal, deal_id)
    if deal is None or deal.organization_id != user.organization_id:
        raise NotFoundError("Deal not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(deal, key, value)
    await db.flush()
    await db.commit()
    return await _to_read(db, deal)


@router.post(
    "/deals/{deal_id}/quotes",
    response_model=QuoteRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a quote and its DRAFT version 1",
)
async def create_quote(
    deal_id: uuid.UUID, payload: QuoteCreate, user: SalesUser, db: DbSession
) -> QuoteRead:
    deal = await db.get(Deal, deal_id)
    if deal is None or deal.organization_id != user.organization_id:
        raise NotFoundError("Deal not found.")

    quote, _version = await QuoteService.create_quote(
        db,
        deal=deal,
        actor=user,
        title=payload.title,
        payment_terms=payload.payment_terms,
        valid_until=payload.valid_until,
        lines=payload.lines,
    )
    await db.commit()

    versions = await QuoteService.versions_for_quote(db, quote.id)
    return QuoteRead(
        id=quote.id,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
        quote_number=quote.quote_number,
        title=quote.title,
        deal_id=quote.deal_id,
        status=quote.status,
        current_version_number=quote.current_version_number,
        current_version_id=versions[-1].id if versions else None,
        versions=[QuoteVersionSummary.model_validate(v) for v in versions],
    )
