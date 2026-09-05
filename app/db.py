"""Async SQLAlchemy engine and session management (PostgreSQL only)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        if settings.is_testing:
            # asyncpg connections are bound to the event loop that created
            # them. Under pytest, fixtures and tests can run on different
            # loops, and a pooled connection reused across loops raises
            # "attached to a different loop". NullPool opens and closes a
            # connection within a single operation, which removes the problem
            # entirely at the cost of per-query connect latency.
            _engine = create_async_engine(
                settings.active_database_url,
                echo=settings.db_echo,
                poolclass=NullPool,
                future=True,
            )
        else:
            _engine = create_async_engine(
                settings.active_database_url,
                echo=settings.db_echo,
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_pre_ping=True,
                future=True,
            )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session.

    The session is *not* auto-committed: services own their transaction
    boundaries explicitly so that multi-step business transitions stay atomic.
    Any unhandled exception rolls the whole request back.
    """
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def discard_pending(session: AsyncSession, instance: object) -> None:
    """Drop a pending instance after a failed ``begin_nested()`` flush.

    Rolling back a SAVEPOINT already evicts objects that were added inside it,
    so calling ``expunge`` unconditionally raises ``InvalidRequestError:
    Instance is not present in this Session`` — which would surface to the
    caller instead of the ``ConflictError`` the race is supposed to produce.
    """
    if instance in session:
        session.expunge(instance)


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
