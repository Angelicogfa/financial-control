"""FastAPI dependency providers for the assets module.

Scope: asset registry, checklist and fundamentalist analysis.
"""

from __future__ import annotations

from fastapi import Depends

from fincontrol_api.composition import get_uow_factory
from fincontrol_api.core.deps import UoWFactory
from fincontrol_api.modules.assets.use_cases import AssetHandler
from fincontrol_api.modules.portfolio.dependencies import get_portfolio_service
from fincontrol_api.modules.portfolio.service import PortfolioApplicationService


def get_asset_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> AssetHandler:
    """Provide the AssetHandler instance."""
    return AssetHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)
