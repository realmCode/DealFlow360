"""Reusable list-query primitives: pagination, sorting and period filtering.

Every list endpoint shares these so the frontend learns one contract instead of
one per resource, and so the reporting module's ``Period`` filter (PDF A7) and
the list filters cannot drift apart — they resolve the same way because they
call the same code.

Sorting is validated against a per-endpoint allowlist rather than accepting an
arbitrary column name, because ``sort_by`` reaches an ``ORDER BY`` clause.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any

from fastapi import Depends, Query

from app.errors import ValidationError


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class Period(StrEnum):
    """The ranges PDF A7 names, plus the ones a dashboard actually needs."""

    TODAY = "today"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"
    ALL = "all"
    CUSTOM = "custom"


# --------------------------------------------------------------- pagination
@dataclass(slots=True)
class PageParams:
    limit: int
    offset: int


async def page_params(
    limit: Annotated[
        int,
        Query(ge=1, le=200, description="Rows per page (1-200)."),
    ] = 25,
    offset: Annotated[
        int,
        Query(ge=0, description="Rows to skip."),
    ] = 0,
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


Pagination = Annotated[PageParams, Depends(page_params)]


# ------------------------------------------------------------------ sorting
@dataclass(slots=True)
class SortParams:
    sort_by: str | None
    sort_dir: SortDirection

    def resolve(
        self, allowed: dict[str, Any], *, default: str
    ) -> tuple[Any, bool]:
        """Map ``sort_by`` to a column, rejecting anything not allowlisted.

        Returns ``(column, descending)``.
        """
        key = self.sort_by or default
        column = allowed.get(key)
        if column is None:
            raise ValidationError(
                f"Cannot sort by {key!r}.",
                code="INVALID_SORT_FIELD",
                details={"sort_by": key, "allowed": sorted(allowed)},
            )
        return column, self.sort_dir is SortDirection.DESC


async def sort_params(
    sort_by: Annotated[
        str | None,
        Query(description="Field to sort by. See the endpoint's allowed list."),
    ] = None,
    sort_dir: Annotated[
        SortDirection, Query(description="Sort direction.")
    ] = SortDirection.DESC,
) -> SortParams:
    return SortParams(sort_by=sort_by, sort_dir=sort_dir)


Sorting = Annotated[SortParams, Depends(sort_params)]


# ------------------------------------------------------------------- period
@dataclass(slots=True)
class PeriodParams:
    period: Period
    date_from: date | None
    date_to: date | None

    @property
    def is_bounded(self) -> bool:
        return self.date_from is not None or self.date_to is not None

    @property
    def start_at(self) -> datetime | None:
        """Inclusive lower bound as a tz-aware datetime."""
        if self.date_from is None:
            return None
        return datetime.combine(self.date_from, datetime.min.time(), tzinfo=UTC)

    @property
    def end_at(self) -> datetime | None:
        """Exclusive upper bound — ``date_to`` is inclusive for the caller."""
        if self.date_to is None:
            return None
        return datetime.combine(
            self.date_to + timedelta(days=1), datetime.min.time(), tzinfo=UTC
        )

    def describe(self) -> str:
        if self.period is Period.ALL:
            return "All time"
        if self.date_from and self.date_to:
            return f"{self.date_from.isoformat()} to {self.date_to.isoformat()}"
        return self.period.value


def _resolve_period(
    period: Period, date_from: date | None, date_to: date | None
) -> PeriodParams:
    today = datetime.now(UTC).date()

    if period is Period.CUSTOM:
        if date_from is None or date_to is None:
            raise ValidationError(
                "period=custom requires both date_from and date_to.",
                code="PERIOD_RANGE_REQUIRED",
                details={"date_from": str(date_from), "date_to": str(date_to)},
            )
        if date_to < date_from:
            raise ValidationError(
                "date_to cannot precede date_from.",
                code="INVALID_PERIOD_RANGE",
                details={
                    "date_from": date_from.isoformat(),
                    "date_to": date_to.isoformat(),
                },
            )
        return PeriodParams(period=period, date_from=date_from, date_to=date_to)

    if period is Period.ALL:
        return PeriodParams(period=period, date_from=None, date_to=None)

    starts = {
        Period.TODAY: today,
        Period.WEEK: today - timedelta(days=today.weekday()),
        Period.MONTH: today.replace(day=1),
        Period.QUARTER: today.replace(
            month=((today.month - 1) // 3) * 3 + 1, day=1
        ),
        Period.YEAR: today.replace(month=1, day=1),
    }
    return PeriodParams(period=period, date_from=starts[period], date_to=today)


async def period_params(
    period: Annotated[
        Period,
        Query(
            description=(
                "Preset range. Use 'custom' with date_from and date_to for an "
                "explicit window. Both bounds are inclusive."
            )
        ),
    ] = Period.ALL,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> PeriodParams:
    return _resolve_period(period, date_from, date_to)


PeriodFilter = Annotated[PeriodParams, Depends(period_params)]
