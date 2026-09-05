"""Environment-driven application settings.

Every credential and tunable lives here; nothing is hardcoded in business code.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # ---------------------------------------------------------------- jwt
    jwt_secret_key: str = "change-me-dev-only-secret-do-not-use-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    #: bcrypt work factor. 12 is the production default; see
    #: `effective_bcrypt_rounds` for why tests use less.
    bcrypt_rounds: int = 12

    # --------------------------------------------------------------- cors
    cors_origins: str = "*"

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

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

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
