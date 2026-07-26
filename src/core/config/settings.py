"""Centralized settings for Phase 10+ subsystems (auth, subscriptions,
billing, security middleware, monitoring). This is deliberately additive,
not a repo-wide config refactor: every pre-existing subsystem's own
`config.py` (src/market_intelligence/config.py, src/portfolio_intelligence/
config.py, src/backtesting/config.py, src/market_data/config.py,
src/market_data/ingestion/config.py) keeps reading its own env vars via
plain `os.getenv` exactly as before -- nothing about them changes here.

`pydantic-settings` was already an installed dependency with zero callers
anywhere in the codebase before this file. This is the first.

Fail-fast posture: `settings` (the module-level singleton below) is built
at import time, so a genuinely broken production configuration (a real
secret left as the insecure development default) raises immediately at
boot -- see `_reject_insecure_secret_in_production` -- rather than at the
first request that happens to touch it. Development and CI never set
SECRET_KEY (confirmed: no env var is exported anywhere in
.github/workflows/ci.yml), so a safe, clearly-labeled development default
is used instead of making every non-production run supply one.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_INSECURE_SECRET_KEY = "dev-insecure-secret-key-change-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    # --- Core ---------------------------------------------------------
    environment: str = Field(default="development", alias="BASEERA_ENV")
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/basirah",
        alias="DATABASE_URL",
    )
    # REDIS_URL (a full "redis://[:password@]host:port/db" or
    # "rediss://" DSN, exactly what managed Redis providers -- Railway,
    # Render, Upstash, Redis Cloud, ElastiCache with AUTH -- hand out)
    # takes priority when set. redis_host/redis_port/redis_password
    # remain the fallback for the current default (unauthenticated
    # local Redis) so nothing about local dev or CI changes.
    redis_url: Optional[str] = Field(default=None, alias="REDIS_URL")
    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_password: Optional[str] = Field(default=None, alias="REDIS_PASSWORD")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")

    # --- Security -------------------------------------------------------
    # No safe production default exists for this -- see
    # `_reject_insecure_secret_in_production` below, which is the actual
    # enforcement point, not this field default.
    secret_key: str = Field(default=_DEV_INSECURE_SECRET_KEY, alias="SECRET_KEY")
    cors_allowed_origins_raw: str = Field(default="", alias="CORS_ALLOWED_ORIGINS")
    # Host header validation (Starlette's TrustedHostMiddleware). Empty
    # (the default) means "not enforced" -- every existing deployment
    # keeps working unchanged until this is explicitly set. Required
    # before production sign-off (see docs/PRODUCTION_CONFIGURATION.md);
    # not fail-fast-enforced here because the correct value is
    # topology-dependent (reverse proxy / platform-generated domain)
    # and isn't knowable at this class's own definition time.
    trusted_hosts_raw: str = Field(default="", alias="TRUSTED_HOSTS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # --- Auth token lifetimes -------------------------------------------
    access_token_expire_minutes: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=30, alias="REFRESH_TOKEN_EXPIRE_DAYS")
    email_verification_token_expire_hours: int = Field(
        default=24, alias="EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS"
    )
    password_reset_token_expire_hours: int = Field(default=1, alias="PASSWORD_RESET_TOKEN_EXPIRE_HOURS")

    # --- Subscriptions ----------------------------------------------------
    trial_length_days: int = Field(default=14, alias="TRIAL_LENGTH_DAYS")

    # --- Billing (no real gateway wired -- see src/billing/) -----------------
    billing_noop_auto_approve: bool = Field(default=True, alias="BILLING_NOOP_AUTO_APPROVE")

    # --- Rate limiting / monitoring -------------------------------------------
    rate_limit_enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    sentry_dsn: Optional[str] = Field(default=None, alias="SENTRY_DSN")

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, value: str) -> str:
        allowed = {"development", "staging", "production"}
        normalized = value.strip().lower()
        if normalized not in allowed:
            raise ValueError(f"BASEERA_ENV must be one of {sorted(allowed)}, got {value!r}")
        return normalized

    @property
    def cors_allowed_origins(self) -> List[str]:
        return [origin.strip() for origin in self.cors_allowed_origins_raw.split(",") if origin.strip()]

    @property
    def trusted_hosts(self) -> List[str]:
        return [host.strip() for host in self.trusted_hosts_raw.split(",") if host.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def redis_dsn(self) -> str:
        """The effective Redis connection string every Redis client in
        this codebase should be built from (`redis.Redis.from_url`) --
        the one place "prefer REDIS_URL, else assemble from host/port/
        password" is decided, so a managed-Redis deployment only ever
        needs to set one variable."""
        if self.redis_url:
            return self.redis_url
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/0"

    @model_validator(mode="after")
    def _reject_insecure_secret_in_production(self) -> "Settings":
        """The one real fail-fast guarantee this class provides: a
        production boot with the development default (unset, or copied
        verbatim from .env.example) crashes immediately instead of
        signing real user sessions with a publicly-known key."""
        if self.is_production and self.secret_key == _DEV_INSECURE_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY is unset (or still the development default) while "
                "BASEERA_ENV=production. Set a real, unique SECRET_KEY before "
                "starting the app in production."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
