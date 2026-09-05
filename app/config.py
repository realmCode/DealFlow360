"""Environment-driven application settings.

Every credential and tunable lives here; nothing is hardcoded in business code.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: The value shipped in source control. Refused outside development so a
#: deployment cannot silently sign tokens with a publicly-known key.
PLACEHOLDER_JWT_SECRET = "change-me-dev-only-secret-do-not-use-in-production"

#: Environments where permissive defaults are a bug rather than a convenience.
HARDENED_ENVIRONMENTS = frozenset({"staging", "production"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- app
    app_name: str = "DealFlow360"
    app_version: str = "1.0.0"
    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = True
    api_prefix: str = ""

    # ----------------------------------------------------------- database
    database_url: str = (
        "postgresql+asyncpg://postgres:mysecretpassword@localhost:5433/mydb"
    )
    test_database_url: str = (
        "postgresql+asyncpg://postgres:mysecretpassword@localhost:5433/mydb_test"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False
    #: The test suite pins every async test to one event loop, so pooled
    #: asyncpg connections are safe there. See `app.db.get_engine` for why
    #: this matters: NullPool costs a full connect per statement.
    test_db_pool_size: int = 5
    test_db_max_overflow: int = 10
    #: Escape hatch for running tests outside the single-loop arrangement.
    db_force_nullpool: bool = False

    # ---------------------------------------------------------------- jwt
    jwt_secret_key: str = PLACEHOLDER_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    #: bcrypt work factor. 12 is the production default; see
    #: `effective_bcrypt_rounds` for why tests use less.
    bcrypt_rounds: int = 12

    # --------------------------------------------------------------- cors
    cors_origins: str = "*"
    #: Bearer tokens travel in the Authorization header, so credentialed CORS
    #: is not needed. Leaving it on together with `cors_origins="*"` makes
    #: Starlette echo any requesting origin, which advertises trust in every
    #: site on the internet. Off by default.
    cors_allow_credentials: bool = False

    # ------------------------------------------------------- rate limiting
    rate_limit_enabled: bool = True
    auth_rate_limit_attempts: int = 10
    auth_rate_limit_window_seconds: int = 900

    # ------------------------------------------------- commercial engine
    default_tax_rate_pct: Decimal = Decimal("0.0")
    money_decimal_places: int = 2

    # ----------------------------------------------------- policy engine
    # See README → "Blended Risk Algorithm" for the derivation of each weight.
    risk_discount_overage_weight: Decimal = Decimal("3.0")
    risk_breadth_weight: Decimal = Decimal("5.0")
    risk_margin_weight: Decimal = Decimal("5.0")
    risk_depth_weight: Decimal = Decimal("0.4")
    risk_finance_escalation_threshold: Decimal = Decimal("60.0")

    # ------------------------------------------------------------ signals
    #: Defaults for newly-created organizations. Per-tenant overrides live in
    #: `organization_settings` and are editable via PATCH /admin/settings.
    stalled_deal_days: int = 14
    discount_anomaly_sigma: Decimal = Decimal("2.0")
    discount_anomaly_min_samples: int = 5
    approval_sla_hours: int = 24
    recommendation_min_margin_pct: Decimal = Decimal("0.0")

    # ----------------------------------------------------------- seeding
    seed_default_password: str = "Password123!"

    @field_validator("database_url", "test_database_url")
    @classmethod
    def _require_async_driver(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DealFlow360 requires PostgreSQL with the asyncpg driver "
                "(postgresql+asyncpg://...). SQLite is not supported."
            )
        return v

    @model_validator(mode="after")
    def _refuse_insecure_defaults_when_hardened(self) -> "Settings":
        """Fail fast rather than inherit the demo posture in a real deployment.

        Every one of these is safe and desirable in development: an open CORS
        policy and readable docs are how a reviewer explores the system. In
        staging or production they are defects, so the only correct behaviour
        is to refuse to start.
        """
        if self.environment not in HARDENED_ENVIRONMENTS:
            return self

        problems: list[str] = []
        if self.jwt_secret_key == PLACEHOLDER_JWT_SECRET:
            problems.append(
                "JWT_SECRET_KEY is still the placeholder shipped in source "
                'control. Generate one: python -c "import secrets; '
                'print(secrets.token_urlsafe(64))"'
            )
        if self.cors_origins.strip() == "*":
            problems.append(
                "CORS_ORIGINS must list exact origins; '*' is not permitted."
            )
        if self.debug:
            problems.append("DEBUG must be false.")

        if problems:
            joined = "\n  - ".join(problems)
            raise ValueError(
                f"Refusing to start in {self.environment!r}:\n  - {joined}"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def effective_cors_allow_credentials(self) -> bool:
        """Never combine credentialed CORS with a wildcard origin.

        Starlette echoes the requesting ``Origin`` on preflight when
        ``allow_origins=["*"]`` and ``allow_credentials=True``, which defeats
        the browser's own wildcard-plus-credentials protection and effectively
        trusts every site. Bearer auth needs neither, so collapse the unsafe
        combination rather than trusting the operator to notice.
        """
        if self.cors_origin_list == ["*"]:
            return False
        return self.cors_allow_credentials

    @property
    def docs_enabled(self) -> bool:
        """Interactive docs are a feature in development, a leak in production."""
        return self.environment not in HARDENED_ENVIRONMENTS

    @property
    def is_testing(self) -> bool:
        return self.environment == "test"

    @property
    def active_database_url(self) -> str:
        """The URL the running process should connect to."""
        return self.test_database_url if self.is_testing else self.database_url

    @property
    def effective_bcrypt_rounds(self) -> int:
        """Deliberately weak hashing under test.

        The integration suite creates and authenticates dozens of users; at 12
        rounds that is minutes of pure KDF. The hashing *code path* is
        identical either way, so lowering the work factor costs no coverage —
        and it is impossible to reach in any non-test environment.
        """
        return 4 if self.is_testing else self.bcrypt_rounds


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
