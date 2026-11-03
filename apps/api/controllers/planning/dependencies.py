"""FastAPI dependency providers for Planejar (Phase 48.R8)."""

from __future__ import annotations

from fastapi import Depends

from composition import get_portfolio_service, get_uow_factory
from domain.planning.services import GoalHandler, IncomeForecastHandler
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.unit_of_work import UoWFactory


def get_goal_handler(uow_factory: UoWFactory = Depends(get_uow_factory)) -> GoalHandler:
    """Provide the GoalHandler instance."""
    return GoalHandler(uow_factory=uow_factory)


def get_income_forecast_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> IncomeForecastHandler:
    """Provide the IncomeForecastHandler instance."""
    return IncomeForecastHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)
