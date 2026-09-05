"""Idempotency for retry-able state-changing endpoints.

The guarantee comes from the database, not from application luck: the unique
constraint on ``(organization_id, endpoint, key)`` means two concurrent retries
race to INSERT and exactly one wins. The loser blocks on the index until the
winner's transaction resolves, then either replays the stored response (winner
committed) or proceeds itself (winner rolled back).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import discard_pending
from app.enums import IdempotencyStatus
from app.errors import ConflictError, IdempotencyConflictError
from app.models.idempotency_key import IdempotencyKey
from app.models.user import User
from app.services.audit_service import jsonable

#: Keys older than this are eligible for cleanup; replays outside the window
#: are treated as fresh requests.
RETENTION = timedelta(days=7)


def request_fingerprint(payload: Any) -> str:
    """Stable SHA-256 of a request body, insensitive to key ordering."""
    normalized = json.dumps(jsonable(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode()).hexdigest()


class IdempotencyService:
    @staticmethod
    async def claim(
        session: AsyncSession,
        *,
        key: str | None,
        endpoint: str,
        method: str,
        user: User,
        payload: Any,
    ) -> tuple[IdempotencyKey | None, dict[str, Any] | None]:
        """Reserve a key.

        Returns ``(record, replay)``:

        * ``(None, None)``   — no key supplied; caller proceeds unprotected.
        * ``(record, None)`` — key reserved; caller must run and then call
          :meth:`complete`.
        * ``(record, body)`` — this exact request already succeeded; the caller
          must return ``body`` without repeating any side effect.
        """
        if not key:
            return None, None

        fingerprint = request_fingerprint(payload)

        existing = (
            await session.execute(
                select(IdempotencyKey)
                .where(
                    IdempotencyKey.organization_id == user.organization_id,
                    IdempotencyKey.endpoint == endpoint,
                    IdempotencyKey.key == key,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

        if existing is not None:
            return existing, IdempotencyService._resolve(existing, fingerprint)

        record = IdempotencyKey(
            organization_id=user.organization_id,
            key=key,
            endpoint=endpoint,
            method=method,
            request_hash=fingerprint,
            status=IdempotencyStatus.IN_PROGRESS,
            user_id=user.id,
            expires_at=datetime.now(UTC) + RETENTION,
        )
        try:
        # ``session.add`` must happen *inside* the SAVEPOINT: an object made
        # pending before the savepoint begins survives its rollback, so the
        # next flush retries the same failing INSERT and poisons the outer
        # transaction with PendingRollbackError.
            async with session.begin_nested():
                session.add(record)
                await session.flush()
        except IntegrityError:
            discard_pending(session, record)
            winner = (
                await session.execute(
                    select(IdempotencyKey)
                    .where(
                        IdempotencyKey.organization_id == user.organization_id,
                        IdempotencyKey.endpoint == endpoint,
                        IdempotencyKey.key == key,
                    )
                    .with_for_update()
                )
            ).scalar_one()
            return winner, IdempotencyService._resolve(winner, fingerprint)

        return record, None

    @staticmethod
    def _resolve(
        record: IdempotencyKey, fingerprint: str
    ) -> dict[str, Any] | None:
        if record.request_hash != fingerprint:
            raise IdempotencyConflictError(
                "This Idempotency-Key was already used with a different request "
                "body. Use a new key for a different request.",
                details={"endpoint": record.endpoint, "key": record.key},
            )
        if record.status is IdempotencyStatus.COMPLETED:
            return record.response_body or {}
        if record.status is IdempotencyStatus.IN_PROGRESS:
            raise ConflictError(
                "An identical request is already being processed. Retry shortly.",
                code="IDEMPOTENT_REQUEST_IN_FLIGHT",
                details={"endpoint": record.endpoint, "key": record.key},
            )
        # Previous attempt failed: allow a genuine retry.
        record.status = IdempotencyStatus.IN_PROGRESS
        return None

    @staticmethod
    async def complete(
        session: AsyncSession,
        record: IdempotencyKey | None,
        *,
        status_code: int,
        body: Any,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
    ) -> None:
        if record is None:
            return
        record.status = IdempotencyStatus.COMPLETED
        record.response_status_code = status_code
        record.response_body = jsonable(body)
        record.entity_type = entity_type
        record.entity_id = entity_id
        record.completed_at = datetime.now(UTC)
        await session.flush()

    @staticmethod
    async def fail(session: AsyncSession, record: IdempotencyKey | None) -> None:
        if record is None:
            return
        record.status = IdempotencyStatus.FAILED
        await session.flush()
