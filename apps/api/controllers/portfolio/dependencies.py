"""FastAPI dependency providers for the portfolio module.

Scope: consolidated portfolio, ARCA allocation, snapshots and analytics.
"""

from __future__ import annotations

from fastapi import Depends

from composition import get_market_gateway, get_uow_factory
from controllers.shared.dependencies import UoWFactory
from core.settings import AppSettings, get_settings
from domain.portfolio.services.service import PortfolioApplicationService
from domain.portfolio.services.use_cases import PortfolioHandler
from infra.providers.gateway import CachedMarketGateway


def get_portfolio_service(
    gateway: CachedMarketGateway = Depends(get_market_gateway),
    settings: AppSettings = Depends(get_settings),
) -> PortfolioApplicationService:
    """Provide the PortfolioApplicationService instance."""
    return PortfolioApplicationService(
        gateway=gateway,
        fetch_workers=settings.market_fetch_workers,
        fetch_timeout_seconds=settings.market_fetch_timeout_seconds,
    )


def get_portfolio_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> PortfolioHandler:
    """Provide the PortfolioHandler instance."""
    return PortfolioHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)
