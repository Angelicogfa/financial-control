"""FastAPI dependency providers for the assets module.

Scope: asset registry, checklist and fundamentalist analysis.
"""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from controllers.portfolio.dependencies import get_portfolio_service
from controllers.shared.dependencies import UoWFactory
from domain.assets.services.use_cases import AssetHandler
from domain.portfolio.services.service import PortfolioApplicationService


def get_asset_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> AssetHandler:
    """Provide the AssetHandler instance."""
    return AssetHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)
