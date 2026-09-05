"""Pytest fixtures — integration tests run against real PostgreSQL.

There is no SQLite fallback on purpose: the schema depends on JSONB, partial
unique indexes, ``SELECT ... FOR UPDATE`` and NUMERIC semantics. Testing
against a different engine would verify something we do not ship.

Isolation strategy: the schema is created once per session against
``TEST_DATABASE_URL``, then every test starts from a truncated database. That
is slower than a rollback-per-test wrapper but it lets service code own its own
commits, which is exactly what production does.
"""

from __future__ import annotations


import os
import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

os.environ["ENVIRONMENT"] = "test"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import dispose_engine, get_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, EXPECTED_TABLES  # noqa: E402

SEED_PASSWORD = settings.seed_default_password


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "concurrency: exercises row locking")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Pin every async test to the session event loop.

    The SQLAlchemy engine is session-scoped, and asyncpg connections are bound
    to the loop that created them. Without this, a function-scoped loop would
    inherit pooled connections from a closed loop and fail with
    "attached to a different loop".
    """
    for item in items:
        test_fn = getattr(item, "function", None)
        if test_fn is not None and inspect.iscoroutinefunction(test_fn):
            item.add_marker(pytest.mark.asyncio(loop_scope="session"), append=False)


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _schema() -> AsyncIterator[None]:
    """Create the schema once for the whole session."""
    assert settings.environment == "test"
    assert "mydb_test" in settings.active_database_url, (
        "Refusing to run tests against a non-test database: "
        f"{settings.active_database_url}"
    )
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_engine()


#: One round trip that reports which tables currently hold at least one row.
#: `EXISTS ... LIMIT 1` stops at the first row, so this is an index/heap peek
#: per table rather than a count.
_DIRTY_TABLE_SQL = " UNION ALL ".join(
    f"SELECT '{table}' AS name "
    f'WHERE EXISTS (SELECT 1 FROM public."{table}" LIMIT 1)'
    for table in EXPECTED_TABLES
)


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def _clean_tables() -> AsyncIterator[None]:
    """Reset to a known state between tests, touching only dirty tables.

    Truncating all 38 tables unconditionally was the single largest cost in
    the suite: `TRUNCATE` rewrites each relation's file and forces a sync, and
    on Docker Desktop for Windows the backing filesystem makes that cost
    seconds rather than milliseconds. Profiling showed 2.3-14.8s of *setup*
    per test against 0.07-0.6s of actual test execution.

    Most tests touch a handful of tables, so the fix is to ask which ones are
    actually dirty — one query — and truncate just those. A test that only
    reads pays nothing at all.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        dirty = {row[0] for row in await conn.execute(sa.text(_DIRTY_TABLE_SQL))}
        if not dirty:
            yield
            return

        # DELETE rather than TRUNCATE. TRUNCATE allocates a new relation file
        # per table and syncs the data directory at commit, which benchmarked
        # at a flat ~2.7s here irrespective of how many tables were involved
        # — it is a fixed filesystem barrier, not per-table work, and
        # synchronous_commit does not govern it. DELETE touches only heap
        # pages, and test tables hold tens of rows at most.
        #
        # session_replication_role=replica suspends foreign-key triggers for
        # this transaction, so deletion order does not matter and no CASCADE
        # reasoning is required. Sequences are reset separately, which is
        # cheap because it does not rewrite data files.
        # asyncpg refuses multiple commands in one prepared statement, so
        # these go one at a time. Only dirty tables are touched, so this is a
        # handful of round trips at a few milliseconds each.
        await conn.execute(sa.text("SET LOCAL synchronous_commit = OFF"))
        await conn.execute(sa.text("SET LOCAL session_replication_role = replica"))
        for table in (t for t in reversed(EXPECTED_TABLES) if t in dirty):
            await conn.execute(sa.text(f'DELETE FROM public."{table}"'))
        # audit_events.sequence is an IDENTITY column and tests assert on
        # ordering, so restart it to keep numbering predictable per test.
        if "audit_events" in dirty:
            await conn.execute(
                sa.text(
                    'ALTER TABLE public."audit_events" '
                    "ALTER COLUMN sequence RESTART WITH 1"
                )
            )
    yield


@asynccontextmanager
async def db_session() -> AsyncIterator[AsyncSession]:
    """Direct database access for tests that assert on persisted rows.

    Deliberately a context manager rather than a fixture: pytest-asyncio
    finalises function-scoped async fixtures on a loop that may differ from the
    session loop the engine belongs to, which produces spurious teardown
    errors. ``async with db_session() as s:`` opens and closes inside the
    test's own loop.
    """
    factory = async_sessionmaker(
        bind=get_engine(), class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    async with factory() as s:
        yield s


@pytest_asyncio.fixture(loop_scope="session")
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c


# ---------------------------------------------------------------- helpers
def _is_page(payload: Any) -> bool:
    """True for a ``Page[T]`` envelope: ``{items, total, limit, offset}``."""
    return (
        isinstance(payload, dict)
        and "items" in payload
        and "total" in payload
        and "limit" in payload
        and "offset" in payload
    )


class ApiResponse:
    """Thin proxy over an httpx response that unwraps page envelopes.

    List endpoints return ``{"items": [...], "total": n, ...}``. Assertions
    almost always want the rows, so ``.json()`` returns ``items`` when the
    payload is a page envelope and the raw body otherwise. Tests that need to
    assert on the pagination metadata itself call ``.page()``.

    This keeps a single, obvious convention rather than sprinkling
    ``["items"]`` through every assertion, and means adding pagination to a
    route does not churn unrelated tests.
    """

    __slots__ = ("_response",)

    def __init__(self, response: Any) -> None:
        self._response = response

    def json(self) -> Any:
        payload = self._response.json()
        return payload["items"] if _is_page(payload) else payload

    def page(self) -> dict[str, Any]:
        """The full envelope. Fails if the endpoint is not paginated."""
        payload = self._response.json()
        assert _is_page(payload), (
            f"{self._response.request.method} "
            f"{self._response.request.url} did not return a Page envelope: "
            f"{payload!r}"
        )
        return payload

    def __getattr__(self, name: str) -> Any:
        return getattr(self._response, name)


class Api:
    """Thin authenticated wrapper that fails loudly on unexpected statuses."""

    def __init__(self, client: AsyncClient, token: str | None = None) -> None:
        self._client = client
        self.token = token

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def request(
        self,
        method: str,
        url: str,
        *,
        json: Any = None,
        params: Any = None,
        headers: dict[str, str] | None = None,
        expect: int | tuple[int, ...] | None = None,
    ) -> ApiResponse:
        merged = {**self.headers, **(headers or {})}
        response = await self._client.request(
            method, url, json=json, params=params, headers=merged
        )
        if expect is not None:
            allowed = (expect,) if isinstance(expect, int) else expect
            assert response.status_code in allowed, (
                f"{method} {url} -> {response.status_code} "
                f"(expected {allowed})\n{response.text}"
            )
        return ApiResponse(response)

    async def get(self, url: str, **kw: Any):
        return await self.request("GET", url, **kw)

    async def post(self, url: str, **kw: Any):
        return await self.request("POST", url, **kw)

    async def patch(self, url: str, **kw: Any):
        return await self.request("PATCH", url, **kw)

    async def delete(self, url: str, **kw: Any):
        return await self.request("DELETE", url, **kw)


async def signup(
    client: AsyncClient,
    *,
    email: str,
    password: str = SEED_PASSWORD,
    full_name: str = "Test User",
    role: str = "SALES",
    organization_id: str | None = None,
    organization_name: str | None = None,
    organization_kind: str = "SELLER",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "email": email,
        "password": password,
        "full_name": full_name,
        "role": role,
        "organization_kind": organization_kind,
    }
    if organization_id:
        payload["organization_id"] = organization_id
    else:
        payload["organization_name"] = organization_name or f"Org {email}"
    response = await client.post("/auth/signup", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def login(client: AsyncClient, email: str, password: str = SEED_PASSWORD) -> Api:
    response = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return Api(client, response.json()["tokens"]["access_token"])


@pytest_asyncio.fixture(loop_scope="session")
async def seeded(client: AsyncClient) -> dict[str, Any]:
    """The canonical demo tenant, loaded through the real API + seed script.

    Returns everything a test needs: authenticated clients per role, product
    ids, warehouse ids and the customer profile id.
    """
    from app.db import get_sessionmaker
    from scripts.seed import seed_canonical_data

    factory = get_sessionmaker()
    async with factory() as s:
        result = await seed_canonical_data(s)
        await s.commit()

    sales = await login(client, "sales@techsupply.com")
    manager = await login(client, "manager@techsupply.com")
    finance = await login(client, "finance@techsupply.com")
    ops = await login(client, "ops@techsupply.com")
    admin = await login(client, "admin@techsupply.com")
    customer = await login(client, "customer@acme.com")

    return {
        **result,
        "sales": sales,
        "manager": manager,
        "finance": finance,
        "ops": ops,
        "admin": admin,
        "customer": customer,
        "password": SEED_PASSWORD,
    }


# ---------------------------------------------------- canonical demo quote
CANONICAL_LINES = (
    # (sku, quantity, discount_pct) — the 5-minute demo configuration.
    ("HW-LAPTOP-01", "100", "18"),
    ("HW-MONITOR-27", "100", "16"),
    ("SV-INSTALL-01", "1", "18"),
    ("SB-SUPPORT-01", "1", "0"),
)


async def build_canonical_quote(
    seeded: dict[str, Any],
    *,
    lines: tuple[tuple[str, str, str], ...] = CANONICAL_LINES,
    title: str = "Acme laptop refresh",
) -> dict[str, Any]:
    """Deal -> quote -> lines, exactly as the demo script does."""
    sales: Api = seeded["sales"]
    products = seeded["products"]

    deal = (
        await sales.post(
            "/deals",
            json={
                "name": title,
                "customer_profile_id": seeded["customer_profile_id"],
                "stage": "PROPOSAL",
            },
            expect=201,
        )
    ).json()

    quote = (
        await sales.post(
            f"/deals/{deal['id']}/quotes",
            json={
                "title": title,
                "lines": [
                    {
                        "product_id": products[sku],
                        "quantity": qty,
                        "discount_pct": disc,
                    }
                    for sku, qty, disc in lines
                ],
            },
            expect=201,
        )
    ).json()

    version_id = quote["current_version_id"]
    version = (await sales.get(f"/quote-versions/{version_id}", expect=200)).json()
    return {"deal": deal, "quote": quote, "version": version, "version_id": version_id}


def money(value: Any) -> Decimal:
    """Parse an API money string into an exact Decimal."""
    return Decimal(str(value))


def page_items(payload: Any) -> list[Any]:
    """Unwrap a ``Page[T]`` response, or pass a bare list through.

    List endpoints return ``{"items": [...], "total": n, "limit": n,
    "offset": n}``. This helper keeps assertions readable and lets a test work
    against either shape, since not every list route is paginated (small
    reference collections like policies and warehouses are returned whole).
    """
    if isinstance(payload, dict) and "items" in payload:
        return payload["items"]
    return payload


def page_total(payload: Any) -> int:
    """The unpaginated row count from a ``Page[T]`` response."""
    if isinstance(payload, dict) and "total" in payload:
        return int(payload["total"])
    return len(payload)
