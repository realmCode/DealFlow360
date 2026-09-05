"""Customer portal endpoints.

Every route here requires the ``CUSTOMER`` role. Internal users are rejected
(403) rather than silently served, so the redacted view is never used as a
substitute for the internal one — and the redacted schemas have no cost or
margin fields to leak in the first place.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.dependencies import (
    CustomerUser,
    DbSession,
    IdempotencyKeyHeader,
    InternalUser,
)
from app.schemas.negotiation import (
    ConfirmRequest,
    CounterOfferOutcome,
    NegotiationMessageRead,
    NegotiationThreadRead,
    PortalMessageCreate,
)
from app.schemas.order import ConfirmResponse, OrderPublicRead
from app.schemas.quote import QuotePublicRead, QuotePublicSummary
from app.services.idempotency import IdempotencyService
from app.services.negotiation_service import NegotiationService
from app.services.order_service import OrderService
from app.services.quote_service import QuoteService

router = APIRouter(tags=["portal"])


@router.get(
    "/portal/quotes",
    response_model=list[QuotePublicSummary],
    summary="Quotes issued to your organization",
)
async def list_portal_quotes(
    user: CustomerUser, db: DbSession
) -> list[QuotePublicSummary]:
    items = await NegotiationService.list_quotes(db, user)
    return [QuotePublicSummary(**item) for item in items]


@router.get(
    "/portal/quotes/{quote_id}",
    response_model=QuotePublicRead,
    summary="Quote detail — no cost, no margin, no internal reasoning",
)
async def get_portal_quote(
    quote_id: uuid.UUID, user: CustomerUser, db: DbSession
) -> QuotePublicRead:
    return QuotePublicRead.model_validate(
        await NegotiationService.get_quote_detail(db, quote_id, user)
    )


@router.get(
    "/portal/quotes/{quote_id}/messages",
    response_model=NegotiationThreadRead,
    summary="Negotiation thread for a quote",
)
async def get_portal_messages(
    quote_id: uuid.UUID, user: CustomerUser, db: DbSession
) -> NegotiationThreadRead:
    return NegotiationThreadRead.model_validate(
        await NegotiationService.get_thread(db, quote_id, user)
    )


@router.post(
    "/portal/quotes/{quote_id}/messages",
    response_model=CounterOfferOutcome,
    status_code=status.HTTP_201_CREATED,
    summary="Comment, ask a question, or counter — a counter creates a new version",
)
async def post_portal_message(
    quote_id: uuid.UUID,
    payload: PortalMessageCreate,
    user: CustomerUser,
    db: DbSession,
) -> CounterOfferOutcome:
    result = await NegotiationService.post_message(
        db, quote_id=quote_id, user=user, payload=payload
    )
    await db.commit()
    return CounterOfferOutcome(
        message=NegotiationMessageRead.model_validate(result["message"]),
        new_version_id=result["new_version_id"],
        new_version_number=result["new_version_number"],
        status=result["status"],
        requires_reapproval=result["requires_reapproval"],
        customer_message=result["customer_message"],
    )


@router.post(
    "/portal/quotes/{quote_id}/confirm",
    response_model=ConfirmResponse,
    summary="Accept the quote and create the order (idempotent, transactional)",
)
async def confirm_portal_quote(
    quote_id: uuid.UUID,
    payload: ConfirmRequest,
    user: CustomerUser,
    db: DbSession,
    idempotency_key: IdempotencyKeyHeader,
    request: Request,
) -> ConfirmResponse:
    quote, _thread, profile = await NegotiationService.authorize(db, quote_id, user)

    record, replay = await IdempotencyService.claim(
        db,
        key=idempotency_key,
        endpoint=f"POST /portal/quotes/{quote_id}/confirm",
        method="POST",
        user=user,
        payload=payload.model_dump(),
    )
    if replay is not None:
        await db.commit()
        return ConfirmResponse(
            order=OrderPublicRead.model_validate(replay["order"]),
            message=replay.get("message", "Order already created."),
            idempotent_replay=True,
        )

    version = await QuoteService.latest_customer_visible_version(db, quote.id)
    if version is None:
        from app.errors import NotFoundError

        raise NotFoundError("This quote has no issued version to confirm.")

    order, already_existed = await OrderService.confirm_quote_version(
        db,
        quote=quote,
        version=version,
        profile=profile,
        actor=user,
        acceptance_note=payload.acceptance_note,
    )

    public = await OrderService.to_public(order)
    message = (
        "This quote was already confirmed; returning the existing order."
        if already_existed
        else f"Order {order.order_number} created."
    )
    body = {"order": public, "message": message}
    await IdempotencyService.complete(
        db,
        record,
        status_code=200,
        body=body,
        entity_type="sales_order",
        entity_id=order.id,
    )
    await db.commit()

    return ConfirmResponse(
        order=OrderPublicRead.model_validate(public),
        message=message,
        idempotent_replay=already_existed,
    )


# ------------------------------------------------- internal-side of the thread
@router.get(
    "/quotes/{quote_id}/negotiation",
    response_model=NegotiationThreadRead,
    summary="Negotiation thread as the seller sees it",
)
async def seller_thread(
    quote_id: uuid.UUID, user: InternalUser, db: DbSession
) -> NegotiationThreadRead:
    from sqlalchemy import select

    from app.errors import NotFoundError
    from app.models.negotiation_message import NegotiationMessage
    from app.models.negotiation_thread import NegotiationThread

    quote = await QuoteService.get_quote(db, quote_id, user.organization_id)
    thread = (
        await db.execute(
            select(NegotiationThread).where(NegotiationThread.quote_id == quote.id)
        )
    ).scalars().first()
    if thread is None:
        raise NotFoundError("This quote has not been sent to the customer yet.")

    messages = list(
        (
            await db.execute(
                select(NegotiationMessage)
                .where(NegotiationMessage.thread_id == thread.id)
                .order_by(NegotiationMessage.created_at)
            )
        ).scalars()
    )
    return NegotiationThreadRead(
        id=thread.id,
        quote_id=thread.quote_id,
        quote_version_id=thread.quote_version_id,
        subject=thread.subject,
        status=thread.status,
        message_count=thread.message_count,
        last_message_at=thread.last_message_at,
        messages=[NegotiationMessageRead.model_validate(m) for m in messages],
    )


@router.post(
    "/quotes/{quote_id}/negotiation/reply",
    response_model=NegotiationMessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Reply to the customer in the negotiation thread",
)
async def seller_reply(
    quote_id: uuid.UUID,
    payload: dict,
    user: InternalUser,
    db: DbSession,
) -> NegotiationMessageRead:
    body = str(payload.get("body", "")).strip()
    if not body:
        from app.errors import ValidationError

        raise ValidationError("A reply must have a body.")
    message = await NegotiationService.post_seller_reply(
        db, quote_id=quote_id, user=user, body=body
    )
    await db.commit()
    return NegotiationMessageRead.model_validate(message)
