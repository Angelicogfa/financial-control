"""Build the market gateway from runtime settings (shared by API and worker)."""

from __future__ import annotations

from typing import Protocol

from infra.cache.redis_cache import build_cache_backend
from infra.providers.bcb import BcbSgsProvider
from infra.providers.brapi import BrapiProvider
from infra.providers.gateway import CachedMarketGateway
from infra.providers.tesouro import DEFAULT_TESOURO_CSV_URL, TesouroTransparenteProvider
from infra.providers.yfinance_provider import YFinanceProvider


class MarketSettings(Protocol):
    """Subset of runtime settings the gateway needs (satisfied by fincontrol_config.Settings)."""

    redis_url: str | None
    brapi_token: str | None
    bcb_sgs_base_url: str
    risk_free_rate: float
    default_annual_ipca: float
    default_usd_brl: float
    quote_cache_ttl: int
    fundamentals_cache_ttl: int
    history_cache_ttl: int
    market_miss_cache_ttl: int


def build_market_gateway(settings: MarketSettings) -> CachedMarketGateway:
    """Gateway wired with brapi, Yahoo Finance, BCB SGS, Tesouro Transparente and cache."""
    csv_url = getattr(settings, "tesouro_transparente_csv_url", DEFAULT_TESOURO_CSV_URL)
    return CachedMarketGateway(
        brapi=BrapiProvider(token=settings.brapi_token),
        yfinance=YFinanceProvider(),
        bcb=BcbSgsProvider(
            base_url=settings.bcb_sgs_base_url,
            default_cdi_annual=settings.risk_free_rate,
            default_ipca_annual=settings.default_annual_ipca,
        ),
        tesouro=TesouroTransparenteProvider(csv_url=csv_url),
        cache=build_cache_backend(settings.redis_url),
        quote_ttl_seconds=settings.quote_cache_ttl,
        fundamentals_ttl_seconds=settings.fundamentals_cache_ttl,
        history_ttl_seconds=settings.history_cache_ttl,
        default_usd_brl=settings.default_usd_brl,
        miss_ttl_seconds=settings.market_miss_cache_ttl,
    )
