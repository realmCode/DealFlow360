"""OrderService — quote confirmation and order creation.

Confirmation is the single most dangerous transition in the system: it converts
a negotiation into a financial commitment. It is therefore guarded three deep:

1. **Authorization** — only the customer organization the quote was issued to.
2. **Business gate** — :meth:`ApprovalService.assert_confirmable` rejects
   unapproved, stale, superseded or already-confirmed versions.
3. **Database** — ``sales_orders.quote_version_id`` is UNIQUE, so even a
   perfectly-timed double request cannot produce two orders. The application
   idempotency layer turns that race into a clean replay instead of a 500.

Everything (order, lines, billing schedules, audit events, quote/version state)
happens in one transaction. A failure part-way leaves no order, no schedules
and no confirmed quote.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import discard_pending
from app.enums import (
    AttentionItemType,
    DealStage,
    QuoteStatus,
    QuoteVersionStatus,
    SalesOrderStatus,
)
from app.errors import DuplicateOperationError, NotFoundError
from app.events import EventType
from app.models.customer_profile import CustomerProfile
from app.models.deal import Deal
from app.models.negotiation_thread import NegotiationThread
from app.models.quote import Quote
from app.models.quote_version import QuoteVersion
from app.models.sales_order import SalesOrder
from app.models.sales_order_line import SalesOrderLine
from app.models.user import User
from app.services.approval_service import ApprovalService
from app.services.audit_service import AttentionService, AuditService
from app.services.billing_service import BillingService
from app.services.commercial_engine import CommercialEngine, money, pct


class OrderService:
    # ------------------------------------------------------------- lookups
    @staticmethod
    async def get_order(
        session: AsyncSession, order_id: uuid.UUID, organization_id: uuid.UUID
    ) -> SalesOrder:
        order = await session.get(SalesOrder, order_id)
        if order is None or order.organization_id != organization_id:
            raise NotFoundError("Sales order not found.")
        return order

    @staticmethod
    async def order_for_version(
        session: AsyncSession, version_id: uuid.UUID
    ) -> SalesOrder | None:
        return (
            await session.execute(
                select(SalesOrder).where(SalesOrder.quote_version_id == version_id)
            )
        ).scalar_one_or_none()

    @staticmethod
    async def lines_for_order(
        session: AsyncSession, order_id: uuid.UUID
    ) -> list[SalesOrderLine]:
        return list(
            (
                await session.execute(
                    select(SalesOrderLine)
                    .where(SalesOrderLine.sales_order_id == order_id)
                    .order_by(SalesOrderLine.line_number)
                )
            ).scalars()
        )

    # ------------------------------------------------------------- confirm
    @classmethod
    async def confirm_quote_version(
        cls,
        session: AsyncSession,
        *,
        quote: Quote,
        version: QuoteVersion,
        profile: CustomerProfile,
        actor: User,
        acceptance_note: str | None = None,
    ) -> tuple[SalesOrder, bool]:
        """Confirm a version and materialise the order.

        Returns ``(order, already_existed)``. ``already_existed`` is ``True``
        when the version had already been confirmed, in which case nothing is
        written and the existing order is returned.
        """
        existing = await cls.order_for_version(session, version.id)
        if existing is not None:
            return existing, True

        # Business gate — raises 409 with a machine-readable code.
        await ApprovalService.assert_confirmable(session, version)

        lines = await CommercialEngine.load_lines(session, version.id)
        if not lines:
            raise NotFoundError("This quote version has no lines to order.")

        deal = await session.get(Deal, quote.deal_id)
        assert deal is not None

        now = datetime.now(UTC)
        order_count = (
            await session.execute(
                select(func.count())
                .select_from(SalesOrder)
                .where(SalesOrder.organization_id == quote.organization_id)
            )
        ).scalar_one()

        order = SalesOrder(
            organization_id=quote.organization_id,
            order_number=f"SO-{int(order_count) + 1:05d}",
            deal_id=quote.deal_id,
            quote_id=quote.id,
            quote_version_id=version.id,
            customer_profile_id=profile.id,
            customer_organization_id=profile.customer_organization_id,
            status=SalesOrderStatus.CREATED,
            currency=version.currency,
            payment_terms=version.payment_terms,
            gross_revenue=money(version.gross_revenue),
            total_discount=money(version.total_discount),
            subtotal=money(version.net_revenue),
            tax_amount=money(version.tax_amount),
            total_amount=money(version.total_revenue),
            total_cost=money(version.total_cost),
            margin=money(version.margin),
            margin_pct=pct(version.margin_pct),
            one_time_amount=money(version.one_time_revenue),
            recurring_amount=money(version.recurring_revenue),
            confirmed_by_user_id=actor.id,
            confirmed_at=now,
        )
        try:
        # ``session.add`` must happen *inside* the SAVEPOINT: an object made
        # pending before the savepoint begins survives its rollback, so the
        # next flush retries the same failing INSERT and poisons the outer
        # transaction with PendingRollbackError.
            async with session.begin_nested():
                session.add(order)
                await session.flush()
        except IntegrityError as exc:
            # Lost the race on uq_sales_orders_quote_version_id.
            discard_pending(session, order)
            winner = await cls.order_for_version(session, version.id)
            if winner is not None:
                return winner, True
            raise DuplicateOperationError(
                "This quote version has already been converted into an order."
            ) from exc

        order_lines: list[SalesOrderLine] = []
        for line in lines:
            order_line = SalesOrderLine(
                organization_id=order.organization_id,
                sales_order_id=order.id,
                quote_line_id=line.id,
                product_id=line.product_id,
                line_number=line.line_number,
                description=line.description,
                category=line.category,
                quantity=Decimal(line.quantity),
                unit_list_price=Decimal(line.unit_list_price),
                unit_net_price=Decimal(line.unit_net_price),
                unit_cost=Decimal(line.unit_cost),
                discount_pct=pct(line.discount_pct),
                discount_amount=money(line.discount_amount),
                gross_amount=money(line.gross_amount),
                net_amount=money(line.net_amount),
                tax_amount=money(line.tax_amount),
                total_amount=money(line.total_amount),
                line_cost=money(line.line_cost),
                billing_type=line.billing_type,
                recurring_interval=line.recurring_interval,
                recurring_periods=line.recurring_periods,
                is_stock_tracked=line.is_stock_tracked,
            )
            session.add(order_line)
            order_lines.append(order_line)
        await session.flush()

        # ---------------------------------------------- quote state changes
        version.status = QuoteVersionStatus.CONFIRMED
        version.confirmed_at = now
        quote.status = QuoteStatus.CONFIRMED
        deal.stage = DealStage.CLOSED_WON
        deal.expected_value = money(version.total_revenue)

        thread = (
            await session.execute(
                select(NegotiationThread).where(NegotiationThread.quote_id == quote.id)
            )
        ).scalars().first()
        if thread is not None:
            from app.enums import NegotiationThreadStatus

            thread.status = NegotiationThreadStatus.RESOLVED
        await session.flush()

        await AuditService.emit(
            session,
            EventType.QUOTE_CONFIRMED,
            organization_id=order.organization_id,
            entity_type="quote_version",
            entity_id=version.id,
            actor=actor,
            payload={
                "quote_number": quote.quote_number,
                "version_number": version.version_number,
                "customer": profile.display_name,
                "total_amount": str(order.total_amount),
                "acceptance_note": acceptance_note,
            },
        )
        await AuditService.emit(
            session,
            EventType.ORDER_CREATED,
            organization_id=order.organization_id,
            entity_type="sales_order",
            entity_id=order.id,
            actor=actor,
            payload={
                "order_number": order.order_number,
                "quote_number": quote.quote_number,
                "quote_version_id": str(version.id),
                "line_count": len(order_lines),
                "subtotal": str(order.subtotal),
                "tax_amount": str(order.tax_amount),
                "total_amount": str(order.total_amount),
                "one_time_amount": str(order.one_time_amount),
                "recurring_amount": str(order.recurring_amount),
                "margin_pct": str(order.margin_pct),
            },
        )

        await BillingService.create_schedules_for_order(
            session, order=order, actor=actor, lines=order_lines
        )

        # The deal is closed: retire the alerts that were chasing it.
        for item_type in (
            AttentionItemType.CUSTOMER_RESPONSE_REQUIRED,
            AttentionItemType.ORDER_BLOCKED,
        ):
            await AttentionService.resolve(
                session,
                organization_id=order.organization_id,
                source_type="quote",
                source_id=quote.id,
                item_type=item_type,
                note=f"Confirmed as order {order.order_number}.",
                actor=actor,
            )
        if thread is not None:
            await AttentionService.resolve(
                session,
                organization_id=order.organization_id,
                source_type="negotiation_thread",
                source_id=thread.id,
                note=f"Confirmed as order {order.order_number}.",
                actor=actor,
            )
        return order, False

    # --------------------------------------------------------- serialisation
    @classmethod
    async def to_public(cls, order: SalesOrder) -> dict[str, Any]:
        """Customer-facing receipt: no cost, no margin."""
        return {
            "id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "currency": order.currency,
            "payment_terms": order.payment_terms,
            "subtotal": order.subtotal,
            "tax_amount": order.tax_amount,
            "total_amount": order.total_amount,
            "one_time_amount": order.one_time_amount,
            "recurring_amount": order.recurring_amount,
            "confirmed_at": order.confirmed_at,
        }
