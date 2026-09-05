"""QuoteService — quote/version/line lifecycle and immutability enforcement.

Split out from ``negotiation_service`` so the versioning mechanics have one
owner: creating a revision, superseding the parent and re-running the Decision
Fabric happen together or not at all.

Immutability matrix (enforced in :meth:`assert_editable`):

    DRAFT             -> lines may be PATCHed/DELETEd in place
    PENDING_APPROVAL  -> immutable; create a revision
    APPROVED          -> immutable; create a revision (triggers stale check)
    SENT              -> immutable; create a revision (triggers stale check)
    NEGOTIATING       -> immutable; create a revision (triggers stale check)
    CONFIRMED         -> immutable forever
    REJECTED          -> immutable forever
    SUPERSEDED        -> immutable forever
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    AttentionItemType,
    BillingType,
    NegotiationThreadStatus,
    QuoteStatus,
    QuoteVersionSource,
    QuoteVersionStatus,
    RoleCode,
    Severity,
    TERMINAL_VERSION_STATUSES,
)
from app.errors import (
    BusinessRuleError,
    ConflictError,
    ImmutableVersionError,
    NotFoundError,
)
from app.events import EventType
from app.models.customer_profile import CustomerProfile
from app.models.deal import Deal
from app.models.negotiation_thread import NegotiationThread
from app.models.product import Product
from app.models.quote import Quote
from app.models.quote_line import QuoteLine
from app.models.quote_version import QuoteVersion
from app.models.user import User
from app.services.approval_service import ApprovalService
from app.services.audit_service import AttentionService, AuditService
from app.services.commercial_engine import CommercialEngine, ZERO, money
from app.services.decision_fabric import DecisionFabric, FabricOutcome

if TYPE_CHECKING:  # pragma: no cover
    from app.services.policy_engine import PolicyEvaluation

#: Human guidance attached to every immutability rejection.
_EDIT_GUIDANCE = {
    QuoteVersionStatus.PENDING_APPROVAL: (
        "This version is awaiting approval. Create a revision "
        "(POST /quote-versions/{id}/revisions) to change it."
    ),
    QuoteVersionStatus.APPROVED: (
        "This version is approved and immutable. Create a revision; the existing "
        "approval will be re-checked for staleness."
    ),
    QuoteVersionStatus.SENT: (
        "This version has been sent to the customer and is immutable. Create a "
        "revision to change it."
    ),
    QuoteVersionStatus.NEGOTIATING: (
        "This version is under negotiation and is immutable. Create a revision to "
        "change it."
    ),
    QuoteVersionStatus.CONFIRMED: "Confirmed versions are immutable forever.",
    QuoteVersionStatus.REJECTED: "Rejected versions are immutable forever.",
    QuoteVersionStatus.SUPERSEDED: "Superseded versions are immutable forever.",
}


class QuoteService:
    # -------------------------------------------------------------- lookups
    @staticmethod
    async def get_version(
        session: AsyncSession, version_id: uuid.UUID, organization_id: uuid.UUID
    ) -> QuoteVersion:
        version = await session.get(QuoteVersion, version_id)
        if version is None or version.organization_id != organization_id:
            raise NotFoundError("Quote version not found.")
        return version

    @staticmethod
    async def get_quote(
        session: AsyncSession, quote_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Quote:
        quote = await session.get(Quote, quote_id)
        if quote is None or quote.organization_id != organization_id:
            raise NotFoundError("Quote not found.")
        return quote

    @staticmethod
    async def versions_for_quote(
        session: AsyncSession, quote_id: uuid.UUID
    ) -> list[QuoteVersion]:
        result = await session.execute(
            select(QuoteVersion)
            .where(QuoteVersion.quote_id == quote_id)
            .order_by(QuoteVersion.version_number)
        )
        return list(result.scalars())

    @staticmethod
    async def current_version(
        session: AsyncSession, quote: Quote
    ) -> QuoteVersion | None:
        result = await session.execute(
            select(QuoteVersion)
            .where(
                QuoteVersion.quote_id == quote.id,
                QuoteVersion.version_number == quote.current_version_number,
            )
        )
        return result.scalars().first()

    @staticmethod
    async def latest_customer_visible_version(
        session: AsyncSession, quote_id: uuid.UUID
    ) -> QuoteVersion | None:
        """Newest version a portal user may see — never an internal draft."""
        result = await session.execute(
            select(QuoteVersion)
            .where(
                QuoteVersion.quote_id == quote_id,
                QuoteVersion.status != QuoteVersionStatus.DRAFT,
            )
            .order_by(QuoteVersion.version_number.desc())
        )
        return result.scalars().first()

    @staticmethod
    async def profile_for_quote(
        session: AsyncSession, quote: Quote
    ) -> CustomerProfile:
        result = await session.execute(
            select(CustomerProfile)
            .join(Deal, Deal.customer_profile_id == CustomerProfile.id)
            .where(Deal.id == quote.deal_id)
        )
        profile = result.scalars().first()
        if profile is None:
            raise NotFoundError("Customer profile for this quote no longer exists.")
        return profile

    # ------------------------------------------------------- recalculation
    @classmethod
    async def recalculate(
        cls,
        session: AsyncSession,
        version: QuoteVersion,
        *,
        profile: CustomerProfile | None = None,
    ) -> "PolicyEvaluation":
        """Recompute money *and* governance for a version.

        Every path that changes lines goes through here, so a version's
        persisted totals, risk score and policy results are never out of step
        with each other — ``GET /policy-results`` is a pure read of current
        truth rather than a lazily-computed guess.
        """
        from app.services.policy_engine import PolicyEngine

        lines = await CommercialEngine.load_lines(session, version.id)
        await CommercialEngine.calculate_version(session, version, lines=lines)
        if profile is None:
            quote = await session.get(Quote, version.quote_id)
            assert quote is not None
            profile = await cls.profile_for_quote(session, quote)
        return await PolicyEngine.evaluate_and_persist(
            session, version, lines=lines, profile=profile
        )

    # --------------------------------------------------------- immutability
    @staticmethod
    def assert_editable(version: QuoteVersion) -> None:
        if version.status is QuoteVersionStatus.DRAFT:
            return
        raise ImmutableVersionError(
            _EDIT_GUIDANCE.get(
                version.status, "This version cannot be edited in place."
            ),
            details={
                "quote_version_id": str(version.id),
                "version_number": version.version_number,
                "status": version.status.value,
                "editable_statuses": [QuoteVersionStatus.DRAFT.value],
            },
        )

    @staticmethod
    def assert_revisable(version: QuoteVersion) -> None:
        if version.status in TERMINAL_VERSION_STATUSES:
            raise ConflictError(
                f"A {version.status.value} version is immutable forever and cannot be "
                f"revised. Start a new quote instead.",
                code="VERSION_TERMINAL",
                details={
                    "status": version.status.value,
                    "version_number": version.version_number,
                },
            )

    # ------------------------------------------------------ numbering
    @staticmethod
    async def _next_number(
        session: AsyncSession, model: Any, organization_id: uuid.UUID, prefix: str
    ) -> str:
        count = (
            await session.execute(
                select(func.count())
                .select_from(model)
                .where(model.organization_id == organization_id)
            )
        ).scalar_one()
        return f"{prefix}-{count + 1:05d}"

    # ------------------------------------------------------- create quote
    @classmethod
    async def create_quote(
        cls,
        session: AsyncSession,
        *,
        deal: Deal,
        actor: User,
        title: str,
        payment_terms: Any | None = None,
        valid_until: Any | None = None,
        lines: Sequence[Any] = (),
    ) -> tuple[Quote, QuoteVersion]:
        profile = await session.get(CustomerProfile, deal.customer_profile_id)
        if profile is None:
            raise NotFoundError("Customer profile not found for this deal.")

        quote = Quote(
            organization_id=deal.organization_id,
            quote_number=await cls._next_number(
                session, Quote, deal.organization_id, "Q"
            ),
            title=title,
            deal_id=deal.id,
            created_by_user_id=actor.id,
            status=QuoteStatus.OPEN,
            current_version_number=1,
        )
        session.add(quote)
        await session.flush()

        version = QuoteVersion(
            organization_id=deal.organization_id,
            quote_id=quote.id,
            version_number=1,
            status=QuoteVersionStatus.DRAFT,
            source=QuoteVersionSource.INITIAL,
            created_by_user_id=actor.id,
            currency=profile.currency,
            payment_terms=payment_terms or profile.payment_terms,
            valid_until=valid_until,
        )
        session.add(version)
        await session.flush()

        for payload in lines:
            await cls.add_line(
                session,
                version=version,
                payload=payload,
                actor=actor,
                profile=profile,
                recalculate=False,
            )

        await cls.recalculate(session, version, profile=profile)

        await AuditService.emit(
            session,
            EventType.QUOTE_CREATED,
            organization_id=quote.organization_id,
            entity_type="quote",
            entity_id=quote.id,
            actor=actor,
            payload={
                "quote_number": quote.quote_number,
                "deal_id": str(deal.id),
                "customer": profile.display_name,
                "version_number": 1,
                "line_count": len(lines),
            },
        )
        return quote, version

    # --------------------------------------------------------------- lines
    @classmethod
    async def add_line(
        cls,
        session: AsyncSession,
        *,
        version: QuoteVersion,
        payload: Any,
        actor: User,
        profile: CustomerProfile | None = None,
        recalculate: bool = True,
        line_number: int | None = None,
    ) -> QuoteLine:
        cls.assert_editable(version)

        product = await session.get(Product, payload.product_id)
        if (
            product is None
            or product.organization_id != version.organization_id
            or not product.is_active
        ):
            raise NotFoundError(
                "Product not found in your catalog.",
                details={"product_id": str(payload.product_id)},
            )

        if profile is None:
            quote = await session.get(Quote, version.quote_id)
            assert quote is not None
            profile = await cls.profile_for_quote(session, quote)

        if line_number is None:
            current_max = (
                await session.execute(
                    select(func.coalesce(func.max(QuoteLine.line_number), 0)).where(
                        QuoteLine.quote_version_id == version.id
                    )
                )
            ).scalar_one()
            line_number = int(current_max) + 1

        recurring_periods = (
            getattr(payload, "recurring_periods", None)
            or product.default_recurring_periods
        )
        if product.billing_type is BillingType.ONE_TIME:
            recurring_periods = 1

        line = QuoteLine(
            organization_id=version.organization_id,
            quote_version_id=version.id,
            product_id=product.id,
            line_number=line_number,
            description=getattr(payload, "description", None) or product.name,
            notes=getattr(payload, "notes", None),
            category=product.category,
            quantity=Decimal(payload.quantity),
            unit_list_price=Decimal(
                getattr(payload, "unit_list_price", None) or product.list_price
            ),
            # Cost is *never* client-supplied — it is copied from the catalog.
            unit_cost=Decimal(product.internal_cost),
            discount_pct=Decimal(getattr(payload, "discount_pct", None) or ZERO),
            tax_rate_pct=cls._resolve_tax_rate(product, profile),
            billing_type=product.billing_type,
            recurring_interval=product.recurring_interval,
            recurring_periods=recurring_periods,
            is_stock_tracked=product.is_stock_tracked,
        )
        CommercialEngine.apply_to_line(line)
        session.add(line)
        await session.flush()

        if recalculate:
            await cls.recalculate(session, version, profile=profile)
        return line

    @staticmethod
    def _resolve_tax_rate(product: Product, profile: CustomerProfile) -> Decimal:
        """Product override wins, then the customer's rate, then the default."""
        from app.config import settings

        if Decimal(product.tax_rate_pct) > ZERO:
            return Decimal(product.tax_rate_pct)
        if Decimal(profile.tax_rate_pct) > ZERO:
            return Decimal(profile.tax_rate_pct)
        return Decimal(settings.default_tax_rate_pct)

    @classmethod
    async def update_line(
        cls,
        session: AsyncSession,
        *,
        version: QuoteVersion,
        line: QuoteLine,
        payload: Any,
        recalculate: bool = True,
    ) -> QuoteLine:
        cls.assert_editable(version)
        data = payload.model_dump(exclude_unset=True)

        if "quantity" in data and data["quantity"] is not None:
            line.quantity = Decimal(data["quantity"])
        if "discount_pct" in data and data["discount_pct"] is not None:
            line.discount_pct = Decimal(data["discount_pct"])
        if "unit_list_price" in data and data["unit_list_price"] is not None:
            line.unit_list_price = Decimal(data["unit_list_price"])
        if "description" in data and data["description"] is not None:
            line.description = data["description"]
        if "notes" in data:
            line.notes = data["notes"]
        if "recurring_periods" in data and data["recurring_periods"] is not None:
            if line.billing_type is BillingType.ONE_TIME:
                raise BusinessRuleError(
                    "recurring_periods only applies to recurring products.",
                    details={"billing_type": line.billing_type.value},
                )
            line.recurring_periods = int(data["recurring_periods"])

        CommercialEngine.apply_to_line(line)
        await session.flush()
        if recalculate:
            await cls.recalculate(session, version)
        return line

    @classmethod
    async def delete_line(
        cls, session: AsyncSession, *, version: QuoteVersion, line: QuoteLine
    ) -> None:
        cls.assert_editable(version)
        await session.delete(line)
        await session.flush()
        await cls.recalculate(session, version)

    @staticmethod
    async def get_line(
        session: AsyncSession, version: QuoteVersion, line_id: uuid.UUID
    ) -> QuoteLine:
        line = await session.get(QuoteLine, line_id)
        if line is None or line.quote_version_id != version.id:
            raise NotFoundError("Quote line not found on this version.")
        return line

    # ------------------------------------------------------------- submit
    @classmethod
    async def submit(
        cls,
        session: AsyncSession,
        *,
        version: QuoteVersion,
        actor: User,
        note: str | None = None,
    ) -> FabricOutcome:
        """Submit for approval. Routing happens automatically from policy.

        Sales never has to decide *who* approves — that is the whole point of
        the Decision Fabric.
        """
        if version.status is not QuoteVersionStatus.DRAFT:
            raise ConflictError(
                f"Only DRAFT versions can be submitted; this one is "
                f"{version.status.value}.",
                code="VERSION_NOT_DRAFT",
                details={"status": version.status.value},
            )

        lines = await CommercialEngine.load_lines(session, version.id)
        if not lines:
            raise BusinessRuleError(
                "A quote must have at least one line before it can be submitted.",
                code="EMPTY_QUOTE",
            )

        quote = await session.get(Quote, version.quote_id)
        assert quote is not None

        await AuditService.emit(
            session,
            EventType.QUOTE_SUBMITTED,
            organization_id=version.organization_id,
            entity_type="quote_version",
            entity_id=version.id,
            actor=actor,
            payload={
                "quote_id": str(quote.id),
                "quote_number": quote.quote_number,
                "version_number": version.version_number,
                "line_count": len(lines),
                "note": note,
            },
        )

        parent = (
            await session.get(QuoteVersion, version.parent_version_id)
            if version.parent_version_id
            else None
        )
        outcome = await DecisionFabric.process_version(
            session,
            version=version,
            actor=actor,
            previous_version=parent,
            trigger="SUBMIT",
            create_approval=True,
        )

        if not version.requires_approval:
            # Within policy: auto-approved, and the audit trail says so.
            version.status = QuoteVersionStatus.APPROVED
            version.submitted_at = version.submitted_at or datetime.now(UTC)
            version.approved_at = datetime.now(UTC)
            await session.flush()
            if outcome.evaluation is not None:
                await ApprovalService.record_auto_approval(
                    session,
                    version=version,
                    evaluation=outcome.evaluation,
                    actor=actor,
                )
            await AuditService.emit(
                session,
                EventType.QUOTE_APPROVED,
                organization_id=version.organization_id,
                entity_type="quote_version",
                entity_id=version.id,
                actor=actor,
                payload={
                    "version_number": version.version_number,
                    "auto_approved": True,
                    "reason": (
                        "No policy was violated and the blended risk score is "
                        f"{version.blended_risk_score}, so no human approval is "
                        "required."
                    ),
                },
            )
        return outcome

    # --------------------------------------------------------------- send
    @classmethod
    async def send(
        cls, session: AsyncSession, *, version: QuoteVersion, actor: User, note: str | None
    ) -> NegotiationThread:
        if version.status is not QuoteVersionStatus.APPROVED:
            raise ConflictError(
                f"Only an APPROVED version can be sent to the customer; this one is "
                f"{version.status.value}.",
                code="VERSION_NOT_APPROVED",
                details={"status": version.status.value},
            )

        quote = await session.get(Quote, version.quote_id)
        assert quote is not None
        profile = await cls.profile_for_quote(session, quote)

        version.status = QuoteVersionStatus.SENT
        version.sent_at = datetime.now(UTC)
        await session.flush()

        thread = (
            await session.execute(
                select(NegotiationThread).where(NegotiationThread.quote_id == quote.id)
            )
        ).scalars().first()

        if thread is None:
            thread = NegotiationThread(
                organization_id=quote.organization_id,
                quote_id=quote.id,
                customer_organization_id=profile.customer_organization_id,
                quote_version_id=version.id,
                subject=f"{quote.quote_number} — {quote.title}",
                status=NegotiationThreadStatus.AWAITING_CUSTOMER,
                opened_by_user_id=actor.id,
            )
            session.add(thread)
        else:
            thread.quote_version_id = version.id
            thread.status = NegotiationThreadStatus.AWAITING_CUSTOMER
        await session.flush()

        await AuditService.emit(
            session,
            EventType.QUOTE_SENT,
            organization_id=quote.organization_id,
            entity_type="quote_version",
            entity_id=version.id,
            actor=actor,
            payload={
                "quote_number": quote.quote_number,
                "version_number": version.version_number,
                "customer": profile.display_name,
                "customer_organization_id": str(profile.customer_organization_id),
                "total_revenue": str(money(version.total_revenue)),
                "note": note,
            },
        )
        await AttentionService.upsert(
            session,
            organization_id=quote.organization_id,
            source_type="quote",
            source_id=quote.id,
            item_type=AttentionItemType.CUSTOMER_RESPONSE_REQUIRED,
            severity=Severity.MEDIUM,
            title=f"Awaiting customer response on {quote.quote_number}",
            reason=(
                f"Version {version.version_number} was sent to "
                f"{profile.display_name} and has not been answered yet."
            ),
            impact=(
                f"{money(version.total_revenue)} of pipeline is waiting on the "
                f"customer."
            ),
            owner_role=RoleCode.SALES,
            owner_user_id=quote.created_by_user_id,
            recommended_action="Follow up with the customer to close the quote.",
            deal_id=quote.deal_id,
            quote_id=quote.id,
            detail={"quote_version_id": str(version.id)},
            actor=actor,
        )
        return thread

    # ------------------------------------------------------------ revision
    @classmethod
    async def create_revision(
        cls,
        session: AsyncSession,
        *,
        version: QuoteVersion,
        actor: User,
        reason: str,
        source: QuoteVersionSource = QuoteVersionSource.INTERNAL_REVISION,
        line_updates: dict[uuid.UUID, Any] | None = None,
        add_lines: Sequence[Any] = (),
        remove_line_ids: Sequence[uuid.UUID] = (),
        payment_terms: Any | None = None,
        submit: bool = True,
    ) -> tuple[QuoteVersion, FabricOutcome]:
        """Create the next version, supersede this one, run the Decision Fabric.

        The whole sequence lives in one transaction: there is no window in
        which a superseded version exists without its replacement, or a
        replacement exists without its governance evaluation.
        """
        cls.assert_revisable(version)

        quote = await session.get(Quote, version.quote_id)
        assert quote is not None
        profile = await cls.profile_for_quote(session, quote)

        next_number = int(
            (
                await session.execute(
                    select(func.coalesce(func.max(QuoteVersion.version_number), 0)).where(
                        QuoteVersion.quote_id == quote.id
                    )
                )
            ).scalar_one()
        ) + 1

        new_version = QuoteVersion(
            organization_id=version.organization_id,
            quote_id=quote.id,
            version_number=next_number,
            parent_version_id=version.id,
            status=QuoteVersionStatus.DRAFT,
            source=source,
            revision_reason=reason,
            created_by_user_id=actor.id,
            currency=version.currency,
            payment_terms=payment_terms or version.payment_terms,
            valid_until=version.valid_until,
        )
        session.add(new_version)
        await session.flush()

        removed = set(remove_line_ids)
        updates = line_updates or {}
        source_lines = await CommercialEngine.load_lines(session, version.id)

        for old_line in source_lines:
            if old_line.id in removed:
                continue
            clone = QuoteLine(
                organization_id=new_version.organization_id,
                quote_version_id=new_version.id,
                source_line_id=old_line.id,
                product_id=old_line.product_id,
                product_variant_id=old_line.product_variant_id,
                line_number=old_line.line_number,
                description=old_line.description,
                notes=old_line.notes,
                category=old_line.category,
                quantity=old_line.quantity,
                unit_list_price=old_line.unit_list_price,
                unit_cost=old_line.unit_cost,
                discount_pct=old_line.discount_pct,
                tax_rate_pct=old_line.tax_rate_pct,
                billing_type=old_line.billing_type,
                recurring_interval=old_line.recurring_interval,
                recurring_periods=old_line.recurring_periods,
                is_stock_tracked=old_line.is_stock_tracked,
            )
            patch = updates.get(old_line.id)
            if patch is not None:
                data = patch.model_dump(exclude_unset=True)
                if data.get("quantity") is not None:
                    clone.quantity = Decimal(data["quantity"])
                if data.get("discount_pct") is not None:
                    clone.discount_pct = Decimal(data["discount_pct"])
                if data.get("unit_list_price") is not None:
                    clone.unit_list_price = Decimal(data["unit_list_price"])
                if data.get("description") is not None:
                    clone.description = data["description"]
                if "notes" in data:
                    clone.notes = data["notes"]
                if data.get("recurring_periods") is not None:
                    clone.recurring_periods = int(data["recurring_periods"])
            CommercialEngine.apply_to_line(clone)
            session.add(clone)

        await session.flush()

        next_line_number = int(
            (
                await session.execute(
                    select(func.coalesce(func.max(QuoteLine.line_number), 0)).where(
                        QuoteLine.quote_version_id == new_version.id
                    )
                )
            ).scalar_one()
        )
        for payload in add_lines:
            next_line_number += 1
            await cls.add_line(
                session,
                version=new_version,
                payload=payload,
                actor=actor,
                profile=profile,
                recalculate=False,
                line_number=next_line_number,
            )

        remaining = await CommercialEngine.load_lines(session, new_version.id)
        if not remaining:
            raise BusinessRuleError(
                "A revision must keep at least one line.", code="EMPTY_REVISION"
            )

        version.status = QuoteVersionStatus.SUPERSEDED
        version.superseded_at = datetime.now(UTC)
        quote.current_version_number = next_number
        await session.flush()

        # A superseded version's alerts are no longer actionable — nobody can
        # fix the margin on a version that has been replaced. Retire them so
        # the Control Tower only ever shows live problems. The replacement
        # version raises its own items if the problem persists.
        await AttentionService.resolve(
            session,
            organization_id=version.organization_id,
            source_type="quote_version",
            source_id=version.id,
            note=(
                f"Version {version.version_number} was superseded by version "
                f"{next_number}."
            ),
            actor=actor,
        )

        await AuditService.emit(
            session,
            EventType.QUOTE_REVISED,
            organization_id=quote.organization_id,
            entity_type="quote_version",
            entity_id=new_version.id,
            actor=actor,
            payload={
                "quote_number": quote.quote_number,
                "from_version": version.version_number,
                "to_version": next_number,
                "source": source.value,
                "reason": reason,
                "lines_updated": len(updates),
                "lines_added": len(add_lines),
                "lines_removed": len(removed),
            },
        )

        if not submit:
            await CommercialEngine.calculate_version(session, new_version)
            outcome = FabricOutcome(
                quote_id=quote.id,
                quote_version_id=new_version.id,
                previous_version_id=version.id,
                evaluated_at=datetime.now(UTC),
            )
            return new_version, outcome

        # DecisionFabric runs on every revision — no exceptions.
        outcome = await DecisionFabric.process_version(
            session,
            version=new_version,
            actor=actor,
            previous_version=version,
            trigger=(
                "CUSTOMER_COUNTER"
                if source is QuoteVersionSource.CUSTOMER_COUNTER
                else "REVISION"
            ),
            create_approval=True,
        )

        if not new_version.requires_approval:
            new_version.status = QuoteVersionStatus.APPROVED
            new_version.submitted_at = datetime.now(UTC)
            new_version.approved_at = datetime.now(UTC)
            await session.flush()
            if outcome.evaluation is not None:
                await ApprovalService.record_auto_approval(
                    session,
                    version=new_version,
                    evaluation=outcome.evaluation,
                    actor=actor,
                )
            await AuditService.emit(
                session,
                EventType.QUOTE_APPROVED,
                organization_id=version.organization_id,
                entity_type="quote_version",
                entity_id=new_version.id,
                actor=actor,
                payload={
                    "version_number": new_version.version_number,
                    "auto_approved": True,
                    "reason": (
                        "The revised terms violate no policy, so no human approval "
                        "is required."
                    ),
                },
            )
            if source is QuoteVersionSource.CUSTOMER_COUNTER:
                # The customer must be able to act on terms they proposed.
                new_version.status = QuoteVersionStatus.NEGOTIATING
                await session.flush()

        return new_version, outcome
