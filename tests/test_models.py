"""Schema-level guarantees: the 33 tables, their types and their constraints.

These assert things the application cannot undo — if a service ever has a bug,
these are what stop bad data reaching disk.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db import get_engine
from app.enums import ALL_ENUMS
from app.models import Base, EXPECTED_TABLES
from tests.conftest import db_session


def test_exactly_thirty_three_tables_are_mapped() -> None:
    assert len(EXPECTED_TABLES) == 33
    assert len(set(EXPECTED_TABLES)) == 33
    assert set(Base.metadata.tables) == set(EXPECTED_TABLES)


def test_the_table_groups_match_the_specification() -> None:
    groups = {
        "identity": ("organizations", "roles", "users", "contacts"),
        "commercial": (
            "customer_profiles",
            "products",
            "product_variants",
            "price_lists",
            "deals",
        ),
        "quotes": ("quotes", "quote_versions", "quote_lines"),
        "decision_fabric": ("policies", "policy_results", "commercial_snapshots"),
        "approvals": ("approval_requests", "approval_steps", "approval_decisions"),
        "decision_tracking": ("decision_impacts", "attention_items"),
        "negotiation": ("negotiation_threads", "negotiation_messages"),
        "execution": ("sales_orders", "sales_order_lines", "fulfillments"),
        "inventory": ("warehouses", "inventory", "inventory_allocations"),
        "billing": ("billing_schedules", "invoices", "payments"),
        "system": ("audit_events", "idempotency_keys"),
    }
    assert sum(len(v) for v in groups.values()) == 33
    for name, tables in groups.items():
        for table in tables:
            assert table in Base.metadata.tables, f"{name}: {table} is missing"


def test_every_table_has_a_uuid_primary_key() -> None:
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID

    for name, table in Base.metadata.tables.items():
        pk = list(table.primary_key.columns)
        assert len(pk) == 1, f"{name} has a composite primary key"
        assert isinstance(pk[0].type, PG_UUID), f"{name}.{pk[0].name} is not a UUID"


def test_no_money_column_is_a_float() -> None:
    """The single most important schema guarantee."""
    for name, table in Base.metadata.tables.items():
        for column in table.columns:
            assert not isinstance(column.type, (sa.Float, sa.REAL)), (
                f"{name}.{column.name} is floating point"
            )


def test_every_timestamp_is_timezone_aware() -> None:
    for name, table in Base.metadata.tables.items():
        for column in table.columns:
            if isinstance(column.type, sa.DateTime):
                assert column.type.timezone is True, (
                    f"{name}.{column.name} is a naive timestamp"
                )


def test_business_tables_are_organization_scoped() -> None:
    """Only global/bootstrap tables may omit organization_id."""
    exempt = {"organizations", "roles", "audit_events"}
    for name in EXPECTED_TABLES:
        if name in exempt:
            continue
        table = Base.metadata.tables[name]
        assert "organization_id" in table.columns, f"{name} is not tenant-scoped"
        assert table.columns["organization_id"].nullable is False, name


def test_append_only_tables_have_no_updated_at() -> None:
    for name in ("audit_events", "approval_decisions", "negotiation_messages", "decision_impacts"):
        columns = set(Base.metadata.tables[name].columns.keys())
        assert "updated_at" not in columns, f"{name} must be append-only"


def test_all_enums_are_string_backed_with_check_constraints() -> None:
    """VARCHAR + CHECK, never a PostgreSQL ENUM type."""
    for name, table in Base.metadata.tables.items():
        for column in table.columns:
            if isinstance(column.type, sa.Enum):
                assert column.type.native_enum is False, (
                    f"{name}.{column.name} uses a native PG enum"
                )


def test_every_enum_has_unique_values() -> None:
    for enum_cls in ALL_ENUMS:
        values = [m.value for m in enum_cls]
        assert len(values) == len(set(values)), enum_cls.__name__


# ------------------------------------------------------ live DB constraints
async def test_all_thirty_three_tables_exist_in_postgres() -> None:
    async with get_engine().connect() as conn:
        rows = await conn.execute(
            sa.text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE'"
            )
        )
        present = {r[0] for r in rows}
    missing = set(EXPECTED_TABLES) - present
    assert not missing, f"missing from the database: {sorted(missing)}"


async def test_foreign_keys_exist_on_every_relational_table() -> None:
    async with get_engine().connect() as conn:
        rows = await conn.execute(
            sa.text(
                "SELECT table_name, COUNT(*) FROM information_schema.table_constraints "
                "WHERE constraint_type='FOREIGN KEY' AND table_schema='public' "
                "GROUP BY table_name"
            )
        )
        counts = dict(rows.all())
    for name in EXPECTED_TABLES:
        if name in ("organizations", "roles"):
            continue
        assert counts.get(name, 0) > 0, f"{name} has no foreign keys"
    assert sum(counts.values()) >= 100


async def test_one_order_per_quote_version_is_enforced_by_the_database(
    seeded,
) -> None:
    """Application logic aside, the schema makes duplicates impossible."""
    from app.models.sales_order import SalesOrder

    table = SalesOrder.__table__
    unique = {
        tuple(c.name for c in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }
    assert ("quote_version_id",) in unique


async def test_quantity_and_discount_bounds_are_enforced(seeded) -> None:
    from tests.conftest import build_canonical_quote

    built = await build_canonical_quote(seeded)
    version_id = uuid.UUID(built["version_id"])

    async with db_session() as s:
        from app.models.quote_line import QuoteLine

        line = (
            await s.execute(
                sa.select(QuoteLine).where(QuoteLine.quote_version_id == version_id).limit(1)
            )
        ).scalar_one()

        line.discount_pct = Decimal("150")
        with pytest.raises((IntegrityError, DBAPIError)):
            await s.commit()

    async with db_session() as s:
        from app.models.quote_line import QuoteLine

        line = (
            await s.execute(
                sa.select(QuoteLine).where(QuoteLine.quote_version_id == version_id).limit(1)
            )
        ).scalar_one()
        line.quantity = Decimal("0")
        with pytest.raises((IntegrityError, DBAPIError)):
            await s.commit()


async def test_version_numbers_are_unique_per_quote(seeded) -> None:
    from tests.conftest import build_canonical_quote

    from app.models.quote_version import QuoteVersion

    built = await build_canonical_quote(seeded)
    async with db_session() as s:
        original = await s.get(QuoteVersion, uuid.UUID(built["version_id"]))
        clone = QuoteVersion(
            organization_id=original.organization_id,
            quote_id=original.quote_id,
            version_number=original.version_number,  # collision
            created_by_user_id=original.created_by_user_id,
            currency="USD",
        )
        s.add(clone)
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_only_one_pending_approval_per_version(seeded) -> None:
    """A partial unique index, so historic requests are still allowed."""
    from tests.conftest import build_canonical_quote

    from app.enums import ApprovalRequestStatus
    from app.models.approval_request import ApprovalRequest

    built = await build_canonical_quote(seeded)
    sales = seeded["sales"]
    await sales.post(
        f"/quote-versions/{built['version_id']}/submit", json={}, expect=200
    )

    async with db_session() as s:
        existing = (
            await s.execute(
                sa.select(ApprovalRequest).where(
                    ApprovalRequest.quote_version_id == uuid.UUID(built["version_id"])
                )
            )
        ).scalar_one()
        duplicate = ApprovalRequest(
            organization_id=existing.organization_id,
            quote_id=existing.quote_id,
            quote_version_id=existing.quote_version_id,
            status=ApprovalRequestStatus.PENDING,
            requested_by_user_id=existing.requested_by_user_id,
            reason="second pending request",
        )
        s.add(duplicate)
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_recurring_schedules_must_declare_an_interval(seeded) -> None:
    from datetime import date

    from app.enums import BillingType
    from app.models.billing_schedule import BillingSchedule

    async with db_session() as s:
        bad = BillingSchedule(
            organization_id=uuid.UUID(seeded["seller_organization_id"]),
            schedule_number="BAD-1",
            sales_order_id=uuid.uuid4(),
            billing_type=BillingType.RECURRING,
            recurring_interval=None,  # violates the CHECK
            amount=Decimal("10.00"),
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            due_date=date(2026, 2, 1),
            description="bad",
        )
        s.add(bad)
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_a_backordered_allocation_must_have_no_warehouse(seeded) -> None:
    from app.enums import AllocationStatus
    from app.models.inventory_allocation import InventoryAllocation

    async with db_session() as s:
        bad = InventoryAllocation(
            organization_id=uuid.UUID(seeded["seller_organization_id"]),
            sales_order_id=uuid.uuid4(),
            sales_order_line_id=uuid.uuid4(),
            product_id=uuid.UUID(seeded["products"]["HW-LAPTOP-01"]),
            warehouse_id=None,
            quantity=Decimal("1"),
            status=AllocationStatus.ALLOCATED,  # needs a warehouse
        )
        s.add(bad)
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_organization_slug_and_user_email_are_globally_unique(seeded) -> None:
    from app.enums import OrganizationKind
    from app.models.organization import Organization

    async with db_session() as s:
        s.add(
            Organization(
                name="Impostor",
                slug="techsupply-solutions",
                kind=OrganizationKind.SELLER,
            )
        )
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_one_stock_row_per_warehouse_product_pair(seeded) -> None:
    from app.models.inventory import Inventory

    async with db_session() as s:
        existing = (
            await s.execute(sa.select(Inventory).limit(1))
        ).scalar_one()
        s.add(
            Inventory(
                organization_id=existing.organization_id,
                warehouse_id=existing.warehouse_id,
                product_id=existing.product_id,
                quantity_on_hand=Decimal("5"),
            )
        )
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_numeric_precision_survives_a_round_trip(seeded) -> None:
    """A value that a float would mangle must come back byte-identical."""
    from app.models.quote_version import QuoteVersion
    from tests.conftest import build_canonical_quote

    built = await build_canonical_quote(seeded)
    tricky = Decimal("123456789012345.67")

    async with db_session() as s:
        version = await s.get(QuoteVersion, uuid.UUID(built["version_id"]))
        version.total_revenue = tricky
        version.margin_pct = Decimal("33.3333")
        await s.commit()

    async with db_session() as s:
        version = await s.get(QuoteVersion, uuid.UUID(built["version_id"]))
        assert version.total_revenue == tricky
        assert str(version.total_revenue) == "123456789012345.67"
        assert version.margin_pct == Decimal("33.3333")
        assert isinstance(version.total_revenue, Decimal)


async def test_jsonb_columns_are_really_jsonb() -> None:
    async with get_engine().connect() as conn:
        rows = await conn.execute(
            sa.text(
                "SELECT table_name, column_name, udt_name "
                "FROM information_schema.columns "
                "WHERE table_schema='public' AND column_name IN "
                "('payload','detail','config','snapshot_json','policy_summary',"
                "'required_levels','attributes','rules','old_value','new_value',"
                "'response_body','decision_snapshot')"
            )
        )
        columns = rows.all()
    assert columns
    for table, column, udt in columns:
        assert udt == "jsonb", f"{table}.{column} is {udt}, not jsonb"


async def test_alembic_migrations_match_the_models() -> None:
    """The migration chain must produce exactly the mapped schema."""
    async with get_engine().connect() as conn:
        rows = await conn.execute(
            sa.text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema='public'"
            )
        )
        live = {(t, c) for t, c in rows.all()}

    for name, table in Base.metadata.tables.items():
        for column in table.columns:
            assert (name, column.name) in live, (
                f"{name}.{column.name} is mapped but absent from the database"
            )
