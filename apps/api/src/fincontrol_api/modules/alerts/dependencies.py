"""FastAPI dependency providers for the alerts module.

Scope: portfolio, valuation and data alerts.
"""

from __future__ import annotations

from fastapi import Depends

from fincontrol_api.composition import get_uow_factory
from fincontrol_api.core.deps import UoWFactory
from fincontrol_api.modules.alerts.use_cases import AlertHandler
from fincontrol_api.modules.portfolio.dependencies import get_portfolio_service
from fincontrol_api.modules.portfolio.service import PortfolioApplicationService


def get_alert_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> AlertHandler:
    """Provide the AlertHandler instance."""
    return AlertHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)
