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
            item.add_marker(pytest.mark.asyncio(loop_scope="session"))


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


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def _clean_tables() -> AsyncIterator[None]:
    """Truncate everything between tests so each starts from a known state."""
    engine = get_engine()
    tables = ", ".join(f'public."{t}"' for t in EXPECTED_TABLES)
    async with engine.begin() as conn:
        await conn.execute(sa.text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
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
    ):
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
        return response

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
