"""FastAPI dependency injection providers for Handlers, Services, MarketGateway, and UoW."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from fastapi import Depends
from fincontrol_core.market.bcb import BcbSgsProvider
from fincontrol_core.market.brapi import BrapiProvider
from fincontrol_core.market.cache import build_cache_backend
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.market.yfinance_provider import YFinanceProvider
from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork
from fincontrol_persistence.unit_of_work import SqlAlchemyUnitOfWork

from fincontrol_api.config import AppSettings, get_settings
from fincontrol_api.handlers.asset_handlers import AssetHandler
from fincontrol_api.handlers.portfolio_handlers import (
    EarningHandler,
    PortfolioHandler,
    TransactionHandler,
)
from fincontrol_api.services.portfolio_service import PortfolioApplicationService

UoWFactory = Callable[[], AbstractUnitOfWork]


def get_uow_factory() -> UoWFactory:
    """Return the Unit of Work factory."""
    return SqlAlchemyUnitOfWork


@lru_cache(maxsize=1)
def _singleton_gateway() -> CachedMarketGateway:
    settings = get_settings()
    cache = build_cache_backend(settings.redis_url)
    brapi = BrapiProvider(token=settings.brapi_token)
    yfinance = YFinanceProvider()
    bcb = BcbSgsProvider(
        default_cdi_annual=settings.default_cdi_annual_rate,
        default_ipca_annual=settings.default_ipca_annual_rate,
    )
    return CachedMarketGateway(
        brapi=brapi,
        yfinance=yfinance,
        bcb=bcb,
        cache=cache,
        quote_ttl_seconds=settings.quote_cache_ttl_seconds,
        fundamentals_ttl_seconds=settings.fundamentals_cache_ttl_seconds,
        history_ttl_seconds=settings.history_cache_ttl_seconds,
        default_usd_brl=settings.default_usd_brl_rate,
    )


def get_market_gateway(
    _settings: AppSettings = Depends(get_settings),
) -> CachedMarketGateway:
    """Provide the configured CachedMarketGateway instance."""
    return _singleton_gateway()


def get_portfolio_service(
    gateway: CachedMarketGateway = Depends(get_market_gateway),
    settings: AppSettings = Depends(get_settings),
) -> PortfolioApplicationService:
    """Provide the PortfolioApplicationService instance."""
    return PortfolioApplicationService(
        gateway=gateway, assumptions=settings.projection_assumptions
    )


def get_asset_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> AssetHandler:
    """Provide the AssetHandler instance."""
    return AssetHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)


def get_transaction_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> TransactionHandler:
    """Provide the TransactionHandler instance."""
    return TransactionHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)


def get_earning_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> EarningHandler:
    """Provide the EarningHandler instance."""
    return EarningHandler(uow_factory=uow_factory)


def get_portfolio_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> PortfolioHandler:
    """Provide the PortfolioHandler instance."""
    return PortfolioHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)
