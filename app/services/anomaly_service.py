"""Discount anomaly detection against a rep's own history.

PDF B9 asks for "discount anomaly alerts (a discount well above a **rep's
historical average**)". That is deliberately a different question from the one
`PolicyEngine` answers.

    PolicyEngine asks:  is this discount above the allowed ceiling?
    This module asks:   is this discount unusual *for this person*?

The distinction matters. A rep whose submitted quotes average 4% suddenly
quoting 14% is a behavioural outlier worth a manager's attention even though
14% is comfortably inside a 15% ceiling. A ceiling check is structurally blind
to that drift, because every individual quote is compliant.

Method
------
Mean and sample standard deviation of ``effective_discount_pct`` over the rep's
recent submitted versions, then flag when

    value > mean + sigma x stdev

``sigma`` and the minimum sample size are per-organization settings. The
minimum sample matters: without it a rep's second-ever quote would be measured
against a single data point and almost anything would look anomalous, which
would train managers to ignore the alert.

Deliberately plain statistics rather than a model. The alert has to survive
"why did this fire?" from a sceptical reviewer, so the reason string carries the
arithmetic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import QuoteVersionStatus, Severity
from app.models.quote_version import QuoteVersion
from app.services.commercial_engine import ZERO, pct
from app.services.settings_service import SettingsService

#: How many of the rep's most recent submitted versions form the baseline.
BASELINE_WINDOW = 30

#: Statuses that represent "the rep actually stood behind this number".
#: A DRAFT is not a commitment, so including drafts would let a rep move their
#: own baseline by saving experiments.
_COMMITTED_STATUSES = (
    QuoteVersionStatus.PENDING_APPROVAL,
    QuoteVersionStatus.APPROVED,
    QuoteVersionStatus.SENT,
    QuoteVersionStatus.NEGOTIATING,
    QuoteVersionStatus.CONFIRMED,
    QuoteVersionStatus.REJECTED,
    QuoteVersionStatus.SUPERSEDED,
)


@dataclass(slots=True)
class DiscountBaseline:
    """A rep's historical discounting pattern."""

    user_id: uuid.UUID
    sample_count: int
    mean: Decimal
    stdev: Decimal
    minimum: Decimal
    maximum: Decimal
    #: False when there is not yet enough history to judge against.
    is_reliable: bool
    min_samples: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": str(self.user_id),
            "sample_count": self.sample_count,
            "mean_discount_pct": str(self.mean),
            "stdev": str(self.stdev),
            "min_discount_pct": str(self.minimum),
            "max_discount_pct": str(self.maximum),
            "is_reliable": self.is_reliable,
            "min_samples_required": self.min_samples,
        }


@dataclass(slots=True)
class AnomalyVerdict:
    """The outcome of comparing one value against a baseline."""

    is_anomaly: bool
    value: Decimal
    baseline: DiscountBaseline
    sigma_threshold: Decimal
    #: How many standard deviations above the mean this value sits.
    deviations: Decimal
    #: The absolute discount value at which the alert would trigger.
    trigger_at: Decimal
    severity: Severity
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_anomaly": self.is_anomaly,
            "effective_discount_pct": str(self.value),
            "sigma_threshold": str(self.sigma_threshold),
            "deviations_above_mean": str(self.deviations),
            "trigger_at_pct": str(self.trigger_at),
            "severity": self.severity.value,
            "reason": self.reason,
            "baseline": self.baseline.as_dict(),
        }


def _sqrt(value: Decimal) -> Decimal:
    """Decimal square root, keeping the whole calculation off floats."""
    if value <= ZERO:
        return ZERO
    return value.sqrt()


class AnomalyService:
    @staticmethod
    async def baseline(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        exclude_version_id: uuid.UUID | None = None,
    ) -> DiscountBaseline:
        """Build the rep's discount baseline from their committed versions.

        ``exclude_version_id`` keeps the version being judged out of its own
        baseline, which would otherwise pull the mean toward the outlier and
        suppress the very alert we are trying to raise.
        """
        settings_row = await SettingsService.for_org(session, organization_id)
        min_samples = int(settings_row.discount_anomaly_min_samples)

        stmt = (
            select(QuoteVersion.effective_discount_pct)
            .where(
                QuoteVersion.organization_id == organization_id,
                QuoteVersion.created_by_user_id == user_id,
                QuoteVersion.status.in_(_COMMITTED_STATUSES),
            )
            .order_by(QuoteVersion.created_at.desc())
            .limit(BASELINE_WINDOW)
        )
        if exclude_version_id is not None:
            stmt = stmt.where(QuoteVersion.id != exclude_version_id)

        values = [Decimal(v) for v in (await session.execute(stmt)).scalars()]
        count = len(values)

        if count == 0:
            return DiscountBaseline(
                user_id=user_id,
                sample_count=0,
                mean=pct(ZERO),
                stdev=pct(ZERO),
                minimum=pct(ZERO),
                maximum=pct(ZERO),
                is_reliable=False,
                min_samples=min_samples,
            )

        mean = sum(values, ZERO) / Decimal(count)
        if count > 1:
            variance = sum(((v - mean) ** 2 for v in values), ZERO) / Decimal(
                count - 1
            )
            stdev = _sqrt(variance)
        else:
            stdev = ZERO

        return DiscountBaseline(
            user_id=user_id,
            sample_count=count,
            mean=pct(mean),
            stdev=pct(stdev),
            minimum=pct(min(values)),
            maximum=pct(max(values)),
            is_reliable=count >= min_samples,
            min_samples=min_samples,
        )

    @staticmethod
    def _severity(deviations: Decimal) -> Severity:
        if deviations >= Decimal("4"):
            return Severity.CRITICAL
        if deviations >= Decimal("3"):
            return Severity.HIGH
        return Severity.MEDIUM

    @classmethod
    async def evaluate(
        cls,
        session: AsyncSession,
        *,
        version: QuoteVersion,
        actor_name: str | None = None,
    ) -> AnomalyVerdict:
        """Judge one version's effective discount against its author's history."""
        settings_row = await SettingsService.for_org(
            session, version.organization_id
        )
        sigma = Decimal(settings_row.discount_anomaly_sigma)
        value = pct(Decimal(version.effective_discount_pct or ZERO))

        baseline = await cls.baseline(
            session,
            user_id=version.created_by_user_id,
            organization_id=version.organization_id,
            exclude_version_id=version.id,
        )
        who = actor_name or "this seller"

        if not baseline.is_reliable:
            return AnomalyVerdict(
                is_anomaly=False,
                value=value,
                baseline=baseline,
                sigma_threshold=sigma,
                deviations=pct(ZERO),
                trigger_at=pct(ZERO),
                severity=Severity.LOW,
                reason=(
                    f"No anomaly check performed: {who} has "
                    f"{baseline.sample_count} prior quote(s), and "
                    f"{baseline.min_samples} are required before a personal "
                    f"baseline is statistically meaningful."
                ),
            )

        # With zero spread, any increase above the mean is by definition
        # unusual, but calling a 0.01pp rise a CRITICAL anomaly would be noise.
        # Requiring a strict increase over the mean keeps it honest without a
        # divide-by-zero.
        if baseline.stdev == ZERO:
            is_anomaly = value > baseline.mean
            deviations = pct(ZERO)
            trigger_at = baseline.mean
        else:
            deviations = pct((value - baseline.mean) / baseline.stdev)
            trigger_at = pct(baseline.mean + sigma * baseline.stdev)
            is_anomaly = value > trigger_at

        severity = cls._severity(deviations) if is_anomaly else Severity.LOW

        if is_anomaly:
            reason = (
                f"An effective discount of {value}% is "
                f"{deviations} standard deviations above {who}'s "
                f"{baseline.sample_count}-quote average of {baseline.mean}% "
                f"(spread {baseline.stdev}pp). At the configured "
                f"{sigma}-sigma threshold, anything above {trigger_at}% is "
                f"flagged for review."
            )
        else:
            reason = (
                f"An effective discount of {value}% is consistent with "
                f"{who}'s {baseline.sample_count}-quote average of "
                f"{baseline.mean}% (flag threshold {trigger_at}%)."
            )

        return AnomalyVerdict(
            is_anomaly=is_anomaly,
            value=value,
            baseline=baseline,
            sigma_threshold=sigma,
            deviations=deviations,
            trigger_at=trigger_at,
            severity=severity,
            reason=reason,
        )
