"""Sliding-window rate limiting for the authentication routes.

Scope is deliberately narrow. Only ``/auth/*`` is limited, because that is the
only unauthenticated write surface: everything else already requires a valid
bearer token, so an attacker must first get past this layer.

Two keys are tracked per attempt so neither axis alone is sufficient to evade
the limit:

* the client IP — stops one host cycling through many accounts
* the submitted email — stops a distributed attack concentrating on one account

State is in-process. That is correct for a single-worker deployment and for the
hackathon demo; behind multiple workers each process would hold its own counters
and the effective limit would multiply by the worker count. Shared state
(Redis, or a database table) would be required for a real multi-worker
deployment, and that is recorded as a known limitation rather than pretended
away.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque

from app.config import settings
from app.errors import RateLimitedError


class SlidingWindowLimiter:
    """Fixed-capacity sliding window keyed by an arbitrary string."""

    def __init__(self, *, attempts: int, window_seconds: int) -> None:
        self._attempts = attempts
        self._window = window_seconds
        self._hits: dict[str, Deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> Deque[float]:
        hits = self._hits[key]
        cutoff = now - self._window
        while hits and hits[0] < cutoff:
            hits.popleft()
        return hits

    def check(self, key: str) -> None:
        """Record an attempt, raising if the window is already full."""
        now = time.monotonic()
        hits = self._prune(key, now)
        if len(hits) >= self._attempts:
            # Retry-After is the time until the oldest hit leaves the window.
            retry_after = max(1, int(self._window - (now - hits[0])) + 1)
            raise RateLimitedError(
                f"Too many attempts. Try again in {retry_after} seconds.",
                retry_after=retry_after,
                details={
                    "limit": self._attempts,
                    "window_seconds": self._window,
                },
            )
        hits.append(now)

    def reset(self, key: str) -> None:
        """Clear a key's history — called after a successful authentication.

        Without this, a user who mistypes their password a few times and then
        succeeds would stay near the limit for the rest of the window.
        """
        self._hits.pop(key, None)

    def clear(self) -> None:
        """Drop all state. Used between tests."""
        self._hits.clear()


_auth_limiter = SlidingWindowLimiter(
    attempts=settings.auth_rate_limit_attempts,
    window_seconds=settings.auth_rate_limit_window_seconds,
)


def enforce_auth_rate_limit(*, ip: str | None, email: str | None) -> None:
    """Raise 429 if either the IP or the email has exhausted its window."""
    if not settings.rate_limit_enabled:
        return
    if ip:
        _auth_limiter.check(f"ip:{ip}")
    if email:
        _auth_limiter.check(f"email:{email.strip().lower()}")


def clear_auth_rate_limit(*, ip: str | None, email: str | None) -> None:
    """Forget a successful authentication's attempts."""
    if ip:
        _auth_limiter.reset(f"ip:{ip}")
    if email:
        _auth_limiter.reset(f"email:{email.strip().lower()}")


def reset_auth_rate_limit_for_tests() -> None:
    _auth_limiter.clear()
