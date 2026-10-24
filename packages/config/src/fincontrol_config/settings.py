"""Single source of runtime configuration, loaded from environment variables or `.env`."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_PREFIX = "change-me"

# Read by docker-compose.yml only (container credentials, published ports).
COMPOSE_ONLY_VARIABLES = frozenset(
    {
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "POSTGRES_PORT",
        "REDIS_PORT",
        "REDIS_PASSWORD",
        "API_PORT",
        "WEB_PORT",
        "PGDATA_VOLUME",
        "REDISDATA_VOLUME",
        "APP_ENV_FILE",
    }
)


class Settings(BaseSettings):
    """Runtime settings. Field names are the lower-case `.env.example` variable names."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Runtime
    app_env: str = "development"
    log_level: str = "INFO"
    log_format: str = Field(default="json", pattern="^(json|text)$")
    tz: str = "America/Sao_Paulo"

    # Storage
    database_url: str = "sqlite:///./fincontrol_dev.db"
    redis_url: str | None = None

    # Market data providers
    brapi_token: str | None = None
    bcb_sgs_base_url: str = "https://api.bcb.gov.br/dados/serie"
    market_fetch_workers: int = Field(default=8, ge=1, le=32)
    market_fetch_timeout_seconds: float = Field(default=20.0, gt=0)

    # Macro fallbacks when BCB / FX providers are unreachable (annual fractions, ADR 0006)
    risk_free_rate: float = 0.1075
    default_annual_ipca: float = 0.045
    default_usd_brl: float = 5.15

    # Cache TTLs (seconds)
    quote_cache_ttl: int = 300
    fundamentals_cache_ttl: int = 86400
    history_cache_ttl: int = 21600

    # Worker schedule and resilience
    quote_refresh_minutes: int = Field(default=15, ge=1)
    bcb_sync_cron_hour: int = Field(default=18, ge=0, le=23)
    bcb_sync_cron_minute: int = Field(default=0, ge=0, le=59)
    snapshot_cron_hour: int = Field(default=18, ge=0, le=23)
    snapshot_cron_minute: int = Field(default=30, ge=0, le=59)
    fundamentals_cron_day_of_week: str = "sun"
    fundamentals_cron_hour: int = Field(default=6, ge=0, le=23)
    job_max_retries: int = Field(default=3, ge=0)
    job_retry_backoff_seconds: float = Field(default=30.0, ge=0)
    job_lock_ttl_seconds: int = Field(default=3600, ge=60)

    # API
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    # Single-user authentication (finding O-03 / TD-01)
    auth_username: str = "admin"
    auth_password_hash: str | None = None
    auth_jwt_secret: str | None = None
    auth_token_ttl_minutes: int = Field(default=720, ge=5)
    auth_cookie_secure: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def auth_configured(self) -> bool:
        """True when a real password hash and JWT secret were provided (not placeholders)."""
        values = (self.auth_password_hash, self.auth_jwt_secret)
        return all(v and not v.startswith(PLACEHOLDER_PREFIX) for v in values)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings instance."""
    return Settings()
