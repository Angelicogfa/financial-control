"""FastAPI dependency injection providers for Handlers, Services, MarketGateway, and UoW."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from fastapi import Depends, Request
from fincontrol_core.market.factory import build_market_gateway
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork
from fincontrol_persistence.health import check_database
from fincontrol_persistence.unit_of_work import SqlAlchemyUnitOfWork

from fincontrol_api.auth import SESSION_COOKIE
from fincontrol_api.config import AppSettings, get_settings, projection_assumptions
from fincontrol_api.handlers.asset_handlers import AssetHandler
from fincontrol_api.handlers.auth_handlers import AuthHandler
from fincontrol_api.handlers.market_handlers import MarketDataHandler
from fincontrol_api.handlers.portfolio_handlers import (
    EarningHandler,
    PortfolioHandler,
    TransactionHandler,
)
from fincontrol_api.handlers.system_handlers import DatabaseProbe, SystemHandler
from fincontrol_api.services.portfolio_service import PortfolioApplicationService

UoWFactory = Callable[[], AbstractUnitOfWork]


def get_uow_factory() -> UoWFactory:
    """Return the Unit of Work factory."""
    return SqlAlchemyUnitOfWork


@lru_cache(maxsize=1)
def _singleton_gateway() -> CachedMarketGateway:
    return build_market_gateway(get_settings())


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
        gateway=gateway,
        assumptions=projection_assumptions(settings),
        fetch_workers=settings.market_fetch_workers,
        fetch_timeout_seconds=settings.market_fetch_timeout_seconds,
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


def get_auth_handler(settings: AppSettings = Depends(get_settings)) -> AuthHandler:
    """Provide the AuthHandler instance."""
    return AuthHandler(settings=settings)


def require_user(
    request: Request,
    handler: AuthHandler = Depends(get_auth_handler),
) -> str:
    """Authenticate the request from the session cookie or a Bearer token."""
    token = request.cookies.get(SESSION_COOKIE)
    header = request.headers.get("Authorization", "")
    if not token and header.lower().startswith("bearer "):
        token = header[7:].strip()
    return handler.authenticate(token)


def get_database_probe() -> DatabaseProbe:
    """Provide the database readiness probe."""
    return check_database


def get_system_handler(
    gateway: CachedMarketGateway = Depends(get_market_gateway),
    database_probe: DatabaseProbe = Depends(get_database_probe),
) -> SystemHandler:
    """Provide the SystemHandler instance."""
    return SystemHandler(gateway=gateway, database_probe=database_probe)


def get_market_data_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> MarketDataHandler:
    """Provide the MarketDataHandler instance."""
    return MarketDataHandler(uow_factory=uow_factory)


def get_portfolio_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> PortfolioHandler:
    """Provide the PortfolioHandler instance."""
    return PortfolioHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)
