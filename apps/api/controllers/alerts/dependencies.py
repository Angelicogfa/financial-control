"""FastAPI dependency providers for the alerts module.

Scope: portfolio, valuation and data alerts.
"""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from controllers.portfolio.dependencies import get_portfolio_service
from controllers.shared.dependencies import UoWFactory
from domain.alerts.services.use_cases import AlertHandler
from domain.portfolio.services.service import PortfolioApplicationService


def get_alert_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> AlertHandler:
    """Provide the AlertHandler instance."""
    return AlertHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)
