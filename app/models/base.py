"""Declarative base, column type aliases and reusable mixins.

Money is **always** ``NUMERIC`` in PostgreSQL and ``Decimal`` in Python.
There is no ``float`` anywhere in the schema.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ---------------------------------------------------------------------------
# Column type aliases
# ---------------------------------------------------------------------------
#: Aggregate monetary amount (order totals, line totals, discounts, margin).
Money = Annotated[Decimal, mapped_column(sa.Numeric(18, 2))]
#: Unit-level monetary amount — 4dp so per-unit prices survive division.
UnitMoney = Annotated[Decimal, mapped_column(sa.Numeric(18, 4))]
#: Percentage stored as a human-readable number: 18.5 means 18.5%.
Percent = Annotated[Decimal, mapped_column(sa.Numeric(9, 4))]
#: Quantity — fractional quantities are legal (e.g. 1.5 hours of service).
Quantity = Annotated[Decimal, mapped_column(sa.Numeric(18, 4))]
#: Ratio/factor with high precision (proration factors).
Factor = Annotated[Decimal, mapped_column(sa.Numeric(12, 8))]

Str32 = Annotated[str, mapped_column(sa.String(32))]
Str64 = Annotated[str, mapped_column(sa.String(64))]
Str128 = Annotated[str, mapped_column(sa.String(128))]
Str255 = Annotated[str, mapped_column(sa.String(255))]
LongText = Annotated[str, mapped_column(sa.Text)]
JsonDict = Annotated[dict[str, Any], mapped_column(JSONB)]
JsonList = Annotated[list[Any], mapped_column(JSONB)]

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map = {
        uuid.UUID: PG_UUID(as_uuid=True),
        Decimal: sa.Numeric(18, 2),
        datetime: sa.DateTime(timezone=True),
        date: sa.Date,
        str: sa.String(255),
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
        bool: sa.Boolean,
        int: sa.Integer,
    }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        ident = getattr(self, "id", None)
        return f"<{type(self).__name__} id={ident}>"


def utcnow_sql() -> sa.TextClause:
    """Server-side default so rows inserted outside the ORM are still stamped."""
    return sa.text("timezone('utc', now())")


def utcnow() -> datetime:
    """Timezone-aware UTC now, evaluated in Python.

    ``onupdate`` deliberately uses this rather than a SQL expression. A
    SQL-expression ``onupdate`` forces SQLAlchemy to post-fetch the column
    after every UPDATE, which leaves the attribute expired; the next plain
    attribute read then attempts synchronous IO and, on an AsyncSession,
    raises ``MissingGreenlet``. Computing it in Python keeps the value
    tz-aware, costs no extra round-trip, and leaves the object usable
    immediately after a flush.
    """
    return datetime.now(UTC)


class UUIDPrimaryKeyMixin:
    """UUID v4 primary key.

    UUIDs are used everywhere because quote/order identifiers are exposed in
    URLs and shared with external portal users: sequential integers would leak
    volume and allow trivial enumeration across tenants.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=utcnow_sql(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=utcnow_sql(),
    )


class CreatedAtMixin:
    """For append-only tables that must never be updated."""

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=utcnow_sql(),
        index=True,
    )


class OrgOwnedMixin:
    """Tenant ownership.

    ``organization_id`` always points at the **selling** organization that owns
    the record. Customer-side visibility is granted through
    ``customer_profiles.customer_organization_id``, never by re-parenting rows.
    """

    @staticmethod
    def _org_fk() -> sa.ForeignKey:
        return sa.ForeignKey("organizations.id", ondelete="RESTRICT")

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )


ZERO = Decimal("0")
ONE_HUNDRED = Decimal("100")
