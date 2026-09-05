"""Database verification: tables, foreign keys, constraints, indexes.

Usage:
    python -m scripts.verify_db            # verify DATABASE_URL
    ENVIRONMENT=test python -m scripts.verify_db   # verify TEST_DATABASE_URL

Exits non-zero if anything expected is missing, so it can gate CI.
"""

from __future__ import annotations

import asyncio
import sys

import sqlalchemy as sa

from app.config import settings
from app.db import dispose_engine, get_engine
from app.models import EXPECTED_TABLES

#: Invariants that must exist in the database itself, not just in Python.
CRITICAL_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    ("sales_orders", "uq_sales_orders_quote_version_id", "one order per quote version"),
    (
        "idempotency_keys",
        "uq_idempotency_keys_organization_id_endpoint_key",
        "idempotency replay protection",
    ),
    ("inventory", "ck_inventory_no_over_reservation", "inventory cannot over-reserve"),
    (
        "inventory",
        "uq_inventory_warehouse_id_product_id",
        "one stock row per warehouse/product",
    ),
    (
        "quote_versions",
        "uq_quote_versions_quote_id_version_number",
        "version numbers unique per quote",
    ),
    (
        "quote_lines",
        "ck_quote_lines_discount_pct_range",
        "discount must be between 0 and 100",
    ),
    (
        "billing_schedules",
        "ck_billing_schedules_recurring_requires_interval",
        "recurring schedules must declare an interval",
    ),
    (
        "sales_order_lines",
        "ck_sales_order_lines_quantity_allocated_within_bounds",
        "cannot allocate more than ordered",
    ),
)

CRITICAL_INDEXES: tuple[tuple[str, str, str], ...] = (
    (
        "approval_requests",
        "uq_approval_requests_one_pending_per_version",
        "only one pending approval per version",
    ),
    (
        "attention_items",
        "uq_attention_items_live_per_source",
        "no duplicate live attention items",
    ),
)

#: Every money/quantity column must be NUMERIC — never double precision.
FLOAT_FORBIDDEN_TYPES = {"double precision", "real"}


async def main() -> int:
    engine = get_engine()
    failures: list[str] = []
    print("=" * 62)
    print("DEALFLOW360 DATABASE VERIFICATION")
    print(f"target: {settings.active_database_url.split('@')[-1]}")
    print("=" * 62)

    async with engine.connect() as conn:
        # ---------------------------------------------------------- tables
        rows = await conn.execute(
            sa.text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE'"
            )
        )
        present = {r[0] for r in rows}
        missing = [t for t in EXPECTED_TABLES if t not in present]
        print(f"\n[tables]   expected 33, found {len(present & set(EXPECTED_TABLES))}")
        if missing:
            failures.append(f"missing tables: {missing}")
            for t in missing:
                print(f"  ✗ {t}")
        else:
            print("  ✓ all 33 business tables present")
        extra = present - set(EXPECTED_TABLES) - {"alembic_version"}
        if extra:
            print(f"  ! unexpected tables: {sorted(extra)}")

        # ----------------------------------------------------- foreign keys
        fk_rows = await conn.execute(
            sa.text(
                "SELECT tc.table_name, COUNT(*) FROM information_schema.table_constraints tc "
                "WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema='public' "
                "GROUP BY tc.table_name"
            )
        )
        fks = dict(fk_rows.all())
        total_fks = sum(fks.values())
        print(f"\n[fks]      {total_fks} foreign keys across {len(fks)} tables")
        tables_needing_fk = [
            t for t in EXPECTED_TABLES if t not in ("organizations", "roles")
        ]
        no_fk = [t for t in tables_needing_fk if fks.get(t, 0) == 0]
        if no_fk:
            failures.append(f"tables without foreign keys: {no_fk}")
            print(f"  ✗ no foreign keys on: {no_fk}")
        else:
            print("  ✓ every relational table has at least one foreign key")

        # ------------------------------------------------------ constraints
        con_rows = await conn.execute(
            sa.text(
                "SELECT table_name, constraint_name FROM information_schema.table_constraints "
                "WHERE table_schema='public'"
            )
        )
        constraints = {(r[0], r[1]) for r in con_rows}
        print(f"\n[constraints] {len(constraints)} total; checking business invariants")
        for table, name, why in CRITICAL_CONSTRAINTS:
            if (table, name) in constraints:
                print(f"  ✓ {table}.{name} — {why}")
            else:
                failures.append(f"missing constraint {table}.{name} ({why})")
                print(f"  ✗ {table}.{name} — {why}")

        # --------------------------------------------------------- indexes
        idx_rows = await conn.execute(
            sa.text(
                "SELECT tablename, indexname FROM pg_indexes WHERE schemaname='public'"
            )
        )
        indexes = {(r[0], r[1]) for r in idx_rows}
        print(f"\n[indexes]  {len(indexes)} total; checking partial unique indexes")
        for table, name, why in CRITICAL_INDEXES:
            if (table, name) in indexes:
                print(f"  ✓ {table}.{name} — {why}")
            else:
                failures.append(f"missing index {table}.{name} ({why})")
                print(f"  ✗ {table}.{name} — {why}")

        # ------------------------------------------------- no float money
        float_rows = await conn.execute(
            sa.text(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema='public' AND data_type IN ('double precision','real')"
            )
        )
        floats = float_rows.all()
        print("\n[money]    scanning for floating-point columns")
        if floats:
            failures.append(f"floating point columns found: {floats}")
            for t, c, d in floats:
                print(f"  ✗ {t}.{c} is {d}")
        else:
            print("  ✓ zero float/double columns — all money is NUMERIC")

        numeric_count = await conn.scalar(
            sa.text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema='public' AND data_type='numeric'"
            )
        )
        print(f"  ✓ {numeric_count} NUMERIC columns")

        # ------------------------------------------------ timezone awareness
        naive_rows = await conn.execute(
            sa.text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND data_type='timestamp without time zone'"
            )
        )
        naive = naive_rows.all()
        print("\n[time]     scanning for naive timestamps")
        if naive:
            failures.append(f"naive timestamp columns: {naive}")
            for t, c in naive:
                print(f"  ✗ {t}.{c}")
        else:
            print("  ✓ all timestamps are timezone-aware")

        version = await conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
        print(f"\n[alembic]  at revision {version}")

    await dispose_engine()

    print("\n" + "=" * 62)
    if failures:
        print(f"VERIFICATION FAILED — {len(failures)} problem(s)")
        for f in failures:
            print(f"  - {f}")
        print("=" * 62)
        return 1
    print("VERIFICATION PASSED")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
