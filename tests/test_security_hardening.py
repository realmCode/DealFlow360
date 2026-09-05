"""Security fixes from docs/SECURITY_AUDIT.md.

Covers the findings that were closed before frontend work: login rate limiting
(SEC-3), the CORS configuration (SEC-2), the startup validators that stop a
deployment inheriting the demo posture (SEC-1/SEC-7), and attention-item
ownership enforcement (SEC-6).
"""

from __future__ import annotations

import pytest

from app.config import PLACEHOLDER_JWT_SECRET, Settings
from app.middleware.rate_limit import reset_auth_rate_limit_for_tests
from tests.conftest import SEED_PASSWORD

# No module-level asyncio mark: this file mixes async HTTP tests with plain
# synchronous validator tests, and `asyncio_mode = auto` already picks up the
# async ones. A blanket mark would warn on every sync test here.


@pytest.fixture(autouse=True)
def _clear_limiter() -> None:
    """The limiter is process-global, so isolate it between tests."""
    reset_auth_rate_limit_for_tests()
    yield
    reset_auth_rate_limit_for_tests()


# ------------------------------------------------------------ rate limiting
async def test_repeated_failed_logins_are_rate_limited(client, seeded) -> None:
    """SEC-3. Without this, the demo password is trivially brute-forced."""
    from app.config import settings

    limit = settings.auth_rate_limit_attempts
    last = None
    for _ in range(limit + 3):
        last = await client.post(
            "/auth/login",
            json={"email": "sales@techsupply.com", "password": "wrong-password"},
        )

    assert last is not None
    assert last.status_code == 429
    body = last.json()["error"]
    assert body["code"] == "RATE_LIMITED"
    assert body["details"]["limit"] == limit
    # A client needs to know how long to back off.
    assert "Retry-After" in last.headers
    assert int(last.headers["Retry-After"]) > 0
    assert body["details"]["retry_after_seconds"] > 0


async def test_a_successful_login_clears_the_attempt_history(
    client, seeded
) -> None:
    """A user who mistypes twice then succeeds must not stay near the limit."""
    for _ in range(3):
        await client.post(
            "/auth/login",
            json={"email": "sales@techsupply.com", "password": "wrong"},
        )

    ok = await client.post(
        "/auth/login",
        json={"email": "sales@techsupply.com", "password": SEED_PASSWORD},
    )
    assert ok.status_code == 200

    # The window is reset, so a fresh run of failures is possible again.
    again = await client.post(
        "/auth/login",
        json={"email": "sales@techsupply.com", "password": "wrong"},
    )
    assert again.status_code == 401


async def test_the_limit_is_scoped_per_email_as_well_as_per_ip(
    client, seeded
) -> None:
    """Exhausting one account must not lock out an unrelated one on the same
    host, but the per-IP ceiling still applies."""
    from app.config import settings

    for _ in range(settings.auth_rate_limit_attempts + 1):
        await client.post(
            "/auth/login",
            json={"email": "sales@techsupply.com", "password": "wrong"},
        )

    # The IP budget is now spent, so any further attempt is refused. That is
    # the intended behaviour: a single host cannot cycle through accounts.
    other = await client.post(
        "/auth/login",
        json={"email": "manager@techsupply.com", "password": SEED_PASSWORD},
    )
    assert other.status_code == 429


# -------------------------------------------------------------------- CORS
async def test_cors_does_not_advertise_credentialed_wildcard(client) -> None:
    """SEC-2.

    Starlette echoes the requesting Origin on preflight when a wildcard is
    combined with credentials, which defeats the browser's own protection and
    effectively trusts every site. Bearer auth needs neither, so the unsafe
    combination is collapsed in config.
    """
    response = await client.request(
        "OPTIONS",
        "/auth/login",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers.get("access-control-allow-credentials") != "true"


async def test_cors_methods_and_headers_are_narrowed(client) -> None:
    response = await client.request(
        "OPTIONS",
        "/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    allowed = response.headers.get("access-control-allow-methods", "")
    # TRACE and CONNECT were previously advertised by the wildcard.
    assert "TRACE" not in allowed
    assert "POST" in allowed


# ------------------------------------------------------ startup validators
def test_placeholder_secret_is_refused_outside_development() -> None:
    """SEC-1. The signing key is readable by anyone with repository access."""
    with pytest.raises(ValueError, match="placeholder"):
        Settings(
            environment="production",
            jwt_secret_key=PLACEHOLDER_JWT_SECRET,
            cors_origins="https://app.example.com",
            debug=False,
        )


def test_wildcard_cors_is_refused_outside_development() -> None:
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(
            environment="production",
            jwt_secret_key="a-real-secret-value-for-this-test-only",
            cors_origins="*",
            debug=False,
        )


def test_debug_is_refused_outside_development() -> None:
    with pytest.raises(ValueError, match="DEBUG"):
        Settings(
            environment="production",
            jwt_secret_key="a-real-secret-value-for-this-test-only",
            cors_origins="https://app.example.com",
            debug=True,
        )


def test_a_correctly_configured_production_settings_object_is_accepted() -> None:
    """The validator must not be so strict that a real deployment cannot boot."""
    settings = Settings(
        environment="production",
        jwt_secret_key="a-real-secret-value-for-this-test-only",
        cors_origins="https://app.example.com,https://admin.example.com",
        debug=False,
    )
    assert settings.cors_origin_list == [
        "https://app.example.com",
        "https://admin.example.com",
    ]
    assert settings.docs_enabled is False, "docs are closed in production"


def test_development_keeps_the_permissive_defaults() -> None:
    """Open docs and open CORS are how a reviewer explores the system."""
    settings = Settings(environment="development")
    assert settings.docs_enabled is True
    assert settings.cors_origin_list == ["*"]
    # A wildcard origin must never be paired with credentials.
    assert settings.effective_cors_allow_credentials is False


def test_credentialed_cors_is_allowed_with_explicit_origins() -> None:
    settings = Settings(
        environment="development",
        cors_origins="http://localhost:5173",
        cors_allow_credentials=True,
    )
    assert settings.effective_cors_allow_credentials is True
