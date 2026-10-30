"""Single source of runtime configuration, loaded from environment variables or `.env`."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_PREFIX = "change-me"
ARGON2_PREFIX = "$argon2"

# Read by the compose files only (container credentials, published ports).
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
    # Longest history range and parallel calls the brapi plan allows (free: 3mo, 1).
    brapi_max_history_range: str | None = "3mo"
    brapi_max_concurrency: int = 1
    bcb_sgs_base_url: str = "https://api.bcb.gov.br/dados/serie"
    tesouro_transparente_csv_url: str = (
        "https://www.tesourodireto.com.br/documents/d/guest/rendimento-investir-csv?download=true"
    )
    tesouro_history_csv_url: str = (
        "https://www.tesourotransparente.gov.br/ckan/dataset/"
        "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
        "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv"
    )
    # CVM open data (Phase 28): IPE disclosures and FCA trading codes.
    cvm_open_data_base_url: str = "https://dados.cvm.gov.br/dados"
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
    market_miss_cache_ttl: int = Field(default=300, ge=0)

    # Worker schedule and resilience
    # Phase 38: the worker stores the quotes of the holdings on this cadence and those of the
    # watchlist on the slower one; screens read the stored values.
    quote_refresh_minutes: int = Field(default=5, ge=1)
    watchlist_refresh_minutes: int = Field(default=60, ge=1)
    # Phase 39: declared distributions every few hours; price history and the catalog
    # indicators once a day after the catalog sync (`catalog_sync_cron_hour`).
    distributions_refresh_hours: int = Field(default=6, ge=1)
    bcb_sync_cron_hour: int = Field(default=18, ge=0, le=23)
    bcb_sync_cron_minute: int = Field(default=0, ge=0, le=59)
    snapshot_cron_hour: int = Field(default=18, ge=0, le=23)
    snapshot_cron_minute: int = Field(default=30, ge=0, le=59)
    fundamentals_cron_day_of_week: str = "sun"
    fundamentals_cron_hour: int = Field(default=6, ge=0, le=23)
    catalog_sync_cron_hour: int = Field(default=19, ge=0, le=23)
    # Phase 28: daily load of the CVM disclosures of held and followed companies.
    cvm_sync_cron_hour: int = Field(default=7, ge=0, le=23)
    # Simulation (Phase 33.1): most traded catalog instruments loaded besides the
    # portfolio and the watchlist (0 = none).
    simulation_catalog_top: int = Field(default=50, ge=0, le=500)
    # Garimpo (Phase 43): liquidity floor of the mining universe (average daily financial
    # volume, R$) and how many stale long histories one daily run reloads.
    mining_min_daily_volume: float = Field(default=1_000_000.0, ge=0)
    mining_history_batch: int = Field(default=60, ge=1, le=1000)
    # Phase 33.3: time limit of one run and how often the worker looks for queued runs.
    simulation_timeout_seconds: int = Field(default=120, ge=5, le=3600)
    simulation_poll_seconds: int = Field(default=15, ge=1, le=3600)
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
        """True when a real Argon2 password hash and JWT secret were provided (not placeholders).

        A plain password or a hash mangled by "$" expansion is rejected here, so the login
        screen reports "not configured" instead of failing every attempt as invalid.
        """
        values = (self.auth_password_hash, self.auth_jwt_secret)
        if not all(v and not v.startswith(PLACEHOLDER_PREFIX) for v in values):
            return False
        return bool(self.auth_password_hash and self.auth_password_hash.startswith(ARGON2_PREFIX))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings instance."""
    return Settings()


AppSettings = Settings
