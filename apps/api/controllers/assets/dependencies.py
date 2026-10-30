"""FastAPI dependency providers for the assets module.

Scope: asset registry, checklist and fundamentalist analysis.
"""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from controllers.portfolio.dependencies import get_portfolio_service
from controllers.shared.dependencies import UoWFactory
from core.settings import AppSettings, get_settings
from domain.assets.services.use_cases import AssetHandler
from domain.forecast.services import ForecastHandler
from domain.portfolio.services.service import PortfolioApplicationService


def get_asset_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> AssetHandler:
    """Provide the AssetHandler instance."""
    return AssetHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)


def get_forecast_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    settings: AppSettings = Depends(get_settings),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> ForecastHandler:
    """Provide the ForecastHandler (Phase 42): reads the stored forecasts, or computes one."""
    return ForecastHandler(
        uow_factory=uow_factory,
        portfolio_service=portfolio_service,
        catalog_top=settings.simulation_catalog_top,
    )
