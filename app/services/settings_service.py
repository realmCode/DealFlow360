"""Per-organization governance settings.

PDF A3 requires the approval chain to be configurable and B9 requires the
stalled-deal window to be "a configured number of days". Both were previously
process-global environment variables, which cannot be per-tenant.

The row is created lazily from the `app.config` defaults on first access, so an
organization that has never opened the settings screen behaves exactly as it did
before this module existed. That property is what makes this change safe to
introduce against an existing database.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.models.organization_settings import OrganizationSettings


class SettingsService:
    @staticmethod
    def _defaults(organization_id: uuid.UUID) -> OrganizationSettings:
        return OrganizationSettings(
            organization_id=organization_id,
            finance_escalation_threshold=app_settings.risk_finance_escalation_threshold,
            risk_discount_overage_weight=app_settings.risk_discount_overage_weight,
            risk_breadth_weight=app_settings.risk_breadth_weight,
            risk_margin_weight=app_settings.risk_margin_weight,
            risk_depth_weight=app_settings.risk_depth_weight,
            stalled_deal_days=app_settings.stalled_deal_days,
            discount_anomaly_sigma=app_settings.discount_anomaly_sigma,
            discount_anomaly_min_samples=app_settings.discount_anomaly_min_samples,
            approval_sla_hours=app_settings.approval_sla_hours,
            recommendation_min_margin_pct=app_settings.recommendation_min_margin_pct,
        )

    @classmethod
    async def for_org(
        cls, session: AsyncSession, organization_id: uuid.UUID
    ) -> OrganizationSettings:
        """Return the tenant's settings, creating them from defaults if absent."""
        existing = (
            await session.execute(
                select(OrganizationSettings).where(
                    OrganizationSettings.organization_id == organization_id
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        row = cls._defaults(organization_id)
        session.add(row)
        try:
            # begin_nested so a lost race does not poison the outer transaction.
            async with session.begin_nested():
                await session.flush()
        except IntegrityError:
            # Another request created it concurrently; adopt the winner.
            from app.db import discard_pending

            discard_pending(session, row)
            return (
                await session.execute(
                    select(OrganizationSettings).where(
                        OrganizationSettings.organization_id == organization_id
                    )
                )
            ).scalar_one()
        return row

    # ----------------------------------------------------- read-only helpers
    #
    # These exist so callers never have to remember the fallback chain. A
    # service that needs one number should not have to know whether the tenant
    # has customised it.

    @classmethod
    async def finance_escalation_threshold(
        cls, session: AsyncSession, organization_id: uuid.UUID
    ) -> Decimal:
        row = await cls.for_org(session, organization_id)
        return Decimal(row.finance_escalation_threshold)

    @classmethod
    async def stalled_deal_days(
        cls, session: AsyncSession, organization_id: uuid.UUID
    ) -> int:
        row = await cls.for_org(session, organization_id)
        return int(row.stalled_deal_days)

    @classmethod
    async def risk_weights(
        cls, session: AsyncSession, organization_id: uuid.UUID
    ) -> dict[str, Decimal]:
        row = await cls.for_org(session, organization_id)
        return {
            "overage": Decimal(row.risk_discount_overage_weight),
            "breadth": Decimal(row.risk_breadth_weight),
            "margin": Decimal(row.risk_margin_weight),
            "depth": Decimal(row.risk_depth_weight),
        }
