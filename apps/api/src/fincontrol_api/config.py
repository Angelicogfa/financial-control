"""Environment-driven application configuration for the FastAPI backend."""

from __future__ import annotations

from functools import lru_cache

from fincontrol_core.portfolio.consolidation import ProjectionAssumptions
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application settings loaded from environment variables or unversioned `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Financial Control API"
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    database_url: str = "sqlite:///./fincontrol_dev.db"
    redis_url: str | None = None
    brapi_token: str | None = None

    quote_cache_ttl_seconds: int = 900
    fundamentals_cache_ttl_seconds: int = 86400
    history_cache_ttl_seconds: int = 21600

    default_cdi_annual_rate: float = 0.1075
    default_ipca_annual_rate: float = 0.045
    default_usd_brl_rate: float = 5.15

    # 12-month projection assumptions (annual fractions, ADR 0006 / finding I-11)
    projection_equity_growth_rate: float = 0.08
    projection_fund_growth_rate: float = 0.10
    projection_real_estate_yield_rate: float = 0.085
    projection_cash_cdi_multiplier: float = 1.0
    projection_cash_income_tax_rate: float = 0.175

    @property
    def projection_assumptions(self) -> ProjectionAssumptions:
        return ProjectionAssumptions(
            equity_capital_growth_rate=self.projection_equity_growth_rate,
            fund_capital_growth_rate=self.projection_fund_growth_rate,
            real_estate_default_yield_rate=self.projection_real_estate_yield_rate,
            cash_cdi_multiplier=self.projection_cash_cdi_multiplier,
            cash_income_tax_rate=self.projection_cash_income_tax_rate,
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached AppSettings instance."""
    return AppSettings()
