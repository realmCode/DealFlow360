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
    """The process-wide engine.

    Test runs are pooled like production. The suite previously forced
    ``NullPool`` because asyncpg connections are bound to the event loop that
    created them, and a pooled connection reused across loops raises
    "attached to a different loop". That workaround is no longer needed:
    ``tests/conftest.py`` pins every async test and fixture to a single
    session-scoped loop, so there is only ever one loop to be bound to.

    It was also extremely expensive. ``NullPool`` opens a fresh TCP connection
    and authentication handshake for *every statement*, measured at ~133 ms
    per query against Dockerised PostgreSQL versus ~4.8 ms pooled — a 28x
    penalty that dominated the whole suite, since a single test issues dozens
    of statements.

    ``DB_FORCE_NULLPOOL=true`` restores the old behaviour for anyone running
    tests outside that single-loop arrangement.
    """
    global _engine
    if _engine is None:
        if settings.db_force_nullpool:
            _engine = create_async_engine(
                settings.active_database_url,
                echo=settings.db_echo,
                poolclass=NullPool,
                future=True,
            )
        elif settings.is_testing:
            _engine = create_async_engine(
                settings.active_database_url,
                echo=settings.db_echo,
                pool_size=settings.test_db_pool_size,
                max_overflow=settings.test_db_max_overflow,
                # Connections are short-lived within a session and the server
                # is local, so pre-ping would add a round trip per checkout
                # for no benefit.
                pool_pre_ping=False,
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
