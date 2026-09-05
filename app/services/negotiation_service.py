"""NegotiationService — the customer portal as a genuinely restricted context.

Authorization model
-------------------
A portal user may touch a quote only when **all** of the following hold:

1. their role is ``CUSTOMER``;
2. their organization equals the quote's
   ``customer_profiles.customer_organization_id``;
3. the quote has actually been issued (a negotiation thread exists).

Failing (2) returns **404**, not 403, so quote ids cannot be enumerated across
customers.

Redaction
---------
Portal responses are built from ``*PublicRead`` schemas which have no cost,
margin, risk or policy fields *at all*. Redaction is a property of the type,
not a filter that a future call site might forget to apply.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    AttentionItemType,
    AuthorKind,
    CUSTOMER_HIDDEN_VERSION_STATUSES,
    NegotiationMessageType,
    NegotiationThreadStatus,
    QuoteVersionSource,
    QuoteVersionStatus,
    RoleCode,
    Severity,
)
from app.errors import BusinessRuleError, ConflictError, NotFoundError
from app.events import EventType
from app.models.customer_profile import CustomerProfile
from app.models.deal import Deal
from app.models.negotiation_message import NegotiationMessage
from app.models.negotiation_thread import NegotiationThread
from app.models.organization import Organization
from app.models.quote import Quote
from app.models.quote_line import QuoteLine
from app.models.quote_version import QuoteVersion
from app.models.user import User
from app.schemas.quote import QuoteLineUpdate
from app.services.approval_service import ApprovalService
from app.services.audit_service import AttentionService, AuditService
from app.services.commercial_engine import CommercialEngine, money, pct
from app.services.quote_service import QuoteService

TRIGGERING_MESSAGE_TYPES = (
    NegotiationMessageType.COUNTER_OFFER,
    NegotiationMessageType.CHANGE_REQUEST,
)


class NegotiationService:
    # ------------------------------------------------------- authorization
    @staticmethod
    async def _accessible_quote_ids(
        session: AsyncSession, user: User
    ) -> list[uuid.UUID]:
        rows = await session.execute(
            select(NegotiationThread.quote_id).where(
                NegotiationThread.customer_organization_id == user.organization_id
            )
        )
        return [row[0] for row in rows]

    @classmethod
    async def authorize(
        cls, session: AsyncSession, quote_id: uuid.UUID, user: User
    ) -> tuple[Quote, NegotiationThread, CustomerProfile]:
        """Resolve a quote for a portal user or raise 404."""
        row = (
            await session.execute(
                select(Quote, NegotiationThread, CustomerProfile)
                .join(NegotiationThread, NegotiationThread.quote_id == Quote.id)
                .join(Deal, Deal.id == Quote.deal_id)
                .join(CustomerProfile, CustomerProfile.id == Deal.customer_profile_id)
                .where(
                    Quote.id == quote_id,
                    NegotiationThread.customer_organization_id
                    == user.organization_id,
                    CustomerProfile.customer_organization_id == user.organization_id,
                )
            )
        ).first()
        if row is None:
            raise NotFoundError(
                "Quote not found.",
                details={"reason": "not issued to your organization"},
            )
        quote, thread, profile = row
        return quote, thread, profile

    # ----------------------------------------------------------- read side
    @classmethod
    async def list_quotes(cls, session: AsyncSession, user: User) -> list[dict[str, Any]]:
        quote_ids = await cls._accessible_quote_ids(session, user)
        if not quote_ids:
            return []

        rows = (
            await session.execute(
                select(Quote).where(Quote.id.in_(quote_ids)).order_by(Quote.created_at.desc())
            )
        ).scalars()

        items: list[dict[str, Any]] = []
        for quote in rows:
            version = await QuoteService.latest_customer_visible_version(
                session, quote.id
            )
            if version is None:
                continue
            request = await ApprovalService.latest_request_for_version(
                session, version.id
            )
            blocked = ApprovalService.blocked_reason(version, request)
            items.append(
                {
                    "quote_id": quote.id,
                    "quote_number": quote.quote_number,
                    "title": quote.title,
                    "current_version_id": version.id,
                    "version_number": version.version_number,
                    "status": version.status,
                    "total_revenue": version.total_revenue,
                    "currency": version.currency,
                    "valid_until": version.valid_until,
                    "awaiting_customer": version.status
                    in (QuoteVersionStatus.SENT, QuoteVersionStatus.NEGOTIATING),
                    "can_confirm": blocked is None,
                    "blocked_reason": blocked,
                }
            )
        return items

    @classmethod
    async def get_quote_detail(
        cls, session: AsyncSession, quote_id: uuid.UUID, user: User
    ) -> dict[str, Any]:
        quote, _thread, _profile = await cls.authorize(session, quote_id, user)
        version = await QuoteService.latest_customer_visible_version(session, quote.id)
        if version is None:
            raise NotFoundError("This quote has no issued version yet.")

        lines = await CommercialEngine.load_lines(session, version.id)
        seller = await session.get(Organization, quote.organization_id)
        request = await ApprovalService.latest_request_for_version(session, version.id)
        blocked = ApprovalService.blocked_reason(version, request)

        return {
            "quote_id": quote.id,
            "quote_number": quote.quote_number,
            "title": quote.title,
            "seller_name": seller.name if seller else "",
            "status": quote.status,
            "current_version": {
                "id": version.id,
                "quote_id": quote.id,
                "version_number": version.version_number,
                "status": version.status,
                "currency": version.currency,
                "payment_terms": version.payment_terms,
                "valid_until": version.valid_until,
                "gross_revenue": version.gross_revenue,
                "total_discount": version.total_discount,
                "net_revenue": version.net_revenue,
                "tax_amount": version.tax_amount,
                "total_revenue": version.total_revenue,
                "effective_discount_pct": version.effective_discount_pct,
                "one_time_revenue": version.one_time_revenue,
                "recurring_revenue": version.recurring_revenue,
                "sent_at": version.sent_at,
                "confirmed_at": version.confirmed_at,
                "lines": lines,
            },
            "can_confirm": blocked is None,
            "blocked_reason": blocked,
        }

    @classmethod
    async def get_thread(
        cls, session: AsyncSession, quote_id: uuid.UUID, user: User
    ) -> dict[str, Any]:
        quote, thread, _profile = await cls.authorize(session, quote_id, user)
        messages = list(
            (
                await session.execute(
                    select(NegotiationMessage)
                    .where(NegotiationMessage.thread_id == thread.id)
                    .order_by(NegotiationMessage.created_at)
                )
            ).scalars()
        )
        return {
            "id": thread.id,
            "quote_id": quote.id,
            "quote_version_id": thread.quote_version_id,
            "subject": thread.subject,
            "status": thread.status,
            "message_count": thread.message_count,
            "last_message_at": thread.last_message_at,
            "messages": messages,
        }

    # ---------------------------------------------------------- write side
    @classmethod
    async def post_message(
        cls,
        session: AsyncSession,
        *,
        quote_id: uuid.UUID,
        user: User,
        payload: Any,
    ) -> dict[str, Any]:
        """Append a portal message; counter-offers trigger the revision flow."""
        quote, thread, profile = await cls.authorize(session, quote_id, user)
        version = await QuoteService.latest_customer_visible_version(session, quote.id)
        if version is None:
            raise NotFoundError("This quote has no issued version yet.")
        if version.status is QuoteVersionStatus.CONFIRMED:
            raise ConflictError(
                "This quote has already been confirmed and can no longer be "
                "negotiated.",
                code="ALREADY_CONFIRMED",
            )

        line: QuoteLine | None = None
        if payload.quote_line_id is not None:
            line = await session.get(QuoteLine, payload.quote_line_id)
            if line is None or line.quote_version_id != version.id:
                raise NotFoundError("That line is not on your current quote version.")

        message = NegotiationMessage(
            organization_id=quote.organization_id,
            thread_id=thread.id,
            quote_version_id=version.id,
            quote_line_id=line.id if line is not None else None,
            author_user_id=user.id,
            author_kind=AuthorKind.CUSTOMER,
            author_display_name=user.full_name,
            message_type=payload.message_type,
            body=payload.body,
        )

        if payload.message_type not in TRIGGERING_MESSAGE_TYPES:
            session.add(message)
            thread.message_count += 1
            thread.last_message_at = datetime.now(UTC)
            thread.status = NegotiationThreadStatus.AWAITING_SELLER
            if version.status is QuoteVersionStatus.SENT:
                version.status = QuoteVersionStatus.NEGOTIATING
            await session.flush()

            await AuditService.emit(
                session,
                EventType.CUSTOMER_COMMENTED,
                organization_id=quote.organization_id,
                entity_type="negotiation_message",
                entity_id=message.id,
                actor=user,
                payload={
                    "quote_id": str(quote.id),
                    "quote_number": quote.quote_number,
                    "quote_version_id": str(version.id),
                    "message_type": payload.message_type.value,
                    "quote_line_id": str(line.id) if line else None,
                },
            )
            await AttentionService.upsert(
                session,
                organization_id=quote.organization_id,
                source_type="negotiation_thread",
                source_id=thread.id,
                item_type=AttentionItemType.CUSTOMER_RESPONSE_REQUIRED,
                severity=Severity.MEDIUM,
                title=f"Customer question on {quote.quote_number}",
                reason=f"{profile.display_name} asked: {payload.body[:200]}",
                impact="The customer is waiting for an answer before deciding.",
                owner_role=RoleCode.SALES,
                owner_user_id=quote.created_by_user_id,
                recommended_action="Reply to the customer in the negotiation thread.",
                deal_id=quote.deal_id,
                quote_id=quote.id,
                detail={"message_id": str(message.id)},
                actor=user,
            )
            return {
                "message": message,
                "new_version_id": None,
                "new_version_number": None,
                "status": version.status.value,
                "requires_reapproval": False,
                "customer_message": (
                    "Your message has been sent to the sales team. They will respond "
                    "shortly."
                ),
            }

        # ------------------------------------------------- counter-offer flow
        return await cls._handle_counter_offer(
            session,
            quote=quote,
            thread=thread,
            profile=profile,
            version=version,
            user=user,
            payload=payload,
            message=message,
        )

    @classmethod
    async def _handle_counter_offer(
        cls,
        session: AsyncSession,
        *,
        quote: Quote,
        thread: NegotiationThread,
        profile: CustomerProfile,
        version: QuoteVersion,
        user: User,
        payload: Any,
        message: NegotiationMessage,
    ) -> dict[str, Any]:
        """A counter never edits the sent version — it creates the next one."""
        current_lines = {
            line.id: line for line in await CommercialEngine.load_lines(session, version.id)
        }

        line_updates: dict[uuid.UUID, QuoteLineUpdate] = {}
        requested: list[dict[str, Any]] = []
        for entry in payload.lines:
            target = current_lines.get(entry.quote_line_id)
            if target is None:
                raise NotFoundError(
                    "One of the requested lines is not on your current quote version.",
                    details={"quote_line_id": str(entry.quote_line_id)},
                )
            fields: dict[str, Any] = {}
            if entry.requested_discount_pct is not None:
                fields["discount_pct"] = Decimal(entry.requested_discount_pct)
            if entry.requested_quantity is not None:
                fields["quantity"] = Decimal(entry.requested_quantity)
            if not fields:
                continue
            line_updates[entry.quote_line_id] = QuoteLineUpdate(**fields)
            requested.append(
                {
                    "quote_line_id": str(entry.quote_line_id),
                    "description": target.description,
                    "current_discount_pct": str(pct(target.discount_pct)),
                    "requested_discount_pct": (
                        str(pct(entry.requested_discount_pct))
                        if entry.requested_discount_pct is not None
                        else None
                    ),
                    "current_quantity": str(target.quantity),
                    "requested_quantity": (
                        str(entry.requested_quantity)
                        if entry.requested_quantity is not None
                        else None
                    ),
                }
            )

        if not line_updates:
            raise BusinessRuleError(
                "The counter-offer did not request any change.",
                code="EMPTY_COUNTER_OFFER",
            )

        first = requested[0]
        message.requested_discount_pct = (
            Decimal(first["requested_discount_pct"])
            if first["requested_discount_pct"]
            else None
        )
        message.requested_quantity = (
            Decimal(first["requested_quantity"])
            if first["requested_quantity"]
            else None
        )
        message.payload = {"requested_lines": requested}
        session.add(message)
        thread.message_count += 1
        thread.last_message_at = datetime.now(UTC)
        thread.status = NegotiationThreadStatus.AWAITING_SELLER
        await session.flush()

        await AuditService.emit(
            session,
            EventType.CUSTOMER_COUNTERED,
            organization_id=quote.organization_id,
            entity_type="negotiation_message",
            entity_id=message.id,
            actor=user,
            payload={
                "quote_id": str(quote.id),
                "quote_number": quote.quote_number,
                "from_version_id": str(version.id),
                "from_version_number": version.version_number,
                "customer": profile.display_name,
                "requested_lines": requested,
                "body": payload.body,
            },
        )

        reason = (
            f"Customer counter-offer from {profile.display_name}: {payload.body[:500]}"
        )
        new_version, outcome = await QuoteService.create_revision(
            session,
            version=version,
            actor=user,
            reason=reason,
            source=QuoteVersionSource.CUSTOMER_COUNTER,
            line_updates=line_updates,
            submit=True,
        )

        message.triggered_version_id = new_version.id
        thread.quote_version_id = new_version.id
        await session.flush()

        requires_reapproval = bool(
            outcome.stale_decisions or outcome.new_approval_request_id
        )
        if requires_reapproval:
            await AttentionService.upsert(
                session,
                organization_id=quote.organization_id,
                source_type="quote",
                source_id=quote.id,
                item_type=AttentionItemType.ORDER_BLOCKED,
                severity=Severity.CRITICAL,
                title=f"Order blocked on {quote.quote_number}",
                reason=(
                    f"{profile.display_name} countered on version "
                    f"{version.version_number}; version "
                    f"{new_version.version_number} needs approval before the order "
                    f"can be created."
                ),
                impact=(
                    f"{money(new_version.total_revenue)} of revenue cannot be booked "
                    f"until the revised quote is approved."
                ),
                owner_role=RoleCode.SALES,
                owner_user_id=quote.created_by_user_id,
                recommended_action=(
                    "Chase the outstanding approval so the customer can confirm."
                ),
                deal_id=quote.deal_id,
                quote_id=quote.id,
                detail={
                    "new_version_id": str(new_version.id),
                    "stale_approval_count": len(outcome.stale_decisions),
                },
                actor=user,
            )
            customer_message = (
                "Thank you — your requested changes have been captured as version "
                f"{new_version.version_number} of this quote. Our team is reviewing "
                "the updated terms and you will be able to confirm once the review "
                "is complete."
            )
        else:
            customer_message = (
                f"Thank you — your requested changes have been applied as version "
                f"{new_version.version_number}. The updated quote is ready for you "
                f"to confirm."
            )

        return {
            "message": message,
            "new_version_id": new_version.id,
            "new_version_number": new_version.version_number,
            "status": new_version.status.value,
            "requires_reapproval": requires_reapproval,
            "customer_message": customer_message,
        }

    # ----------------------------------------------------- seller replies
    @classmethod
    async def post_seller_reply(
        cls,
        session: AsyncSession,
        *,
        quote_id: uuid.UUID,
        user: User,
        body: str,
    ) -> NegotiationMessage:
        quote = await QuoteService.get_quote(session, quote_id, user.organization_id)
        thread = (
            await session.execute(
                select(NegotiationThread).where(NegotiationThread.quote_id == quote.id)
            )
        ).scalars().first()
        if thread is None:
            raise NotFoundError("This quote has not been sent to the customer yet.")

        version = await QuoteService.latest_customer_visible_version(session, quote.id)
        assert version is not None

        message = NegotiationMessage(
            organization_id=quote.organization_id,
            thread_id=thread.id,
            quote_version_id=version.id,
            author_user_id=user.id,
            author_kind=AuthorKind.SELLER,
            author_display_name=user.full_name,
            message_type=NegotiationMessageType.SELLER_REPLY,
            body=body,
        )
        session.add(message)
        thread.message_count += 1
        thread.last_message_at = datetime.now(UTC)
        thread.status = NegotiationThreadStatus.AWAITING_CUSTOMER
        await session.flush()

        await AttentionService.resolve(
            session,
            organization_id=quote.organization_id,
            source_type="negotiation_thread",
            source_id=thread.id,
            item_type=AttentionItemType.CUSTOMER_RESPONSE_REQUIRED,
            note=f"Replied by {user.email}.",
            actor=user,
        )
        return message

    # ------------------------------------------------------------ helpers
    @staticmethod
    def is_hidden_from_customer(version: QuoteVersion) -> bool:
        return version.status in CUSTOMER_HIDDEN_VERSION_STATUSES
