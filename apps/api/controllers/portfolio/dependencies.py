"""FastAPI dependency providers for the portfolio module.

Scope: consolidated portfolio, ARCA allocation, snapshots and analytics.
"""

from __future__ import annotations

from fastapi import Depends

from composition import get_portfolio_service, get_uow_factory
from domain.portfolio.services.income import IncomeHandler
from domain.portfolio.services.service import PortfolioApplicationService
from domain.portfolio.services.use_cases import PortfolioHandler
from domain.shared.unit_of_work import UoWFactory


def get_portfolio_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> PortfolioHandler:
    """Provide the PortfolioHandler instance."""
    return PortfolioHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)


def get_income_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> IncomeHandler:
    """Provide the IncomeHandler instance (Carteira › Proventos)."""
    return IncomeHandler(uow_factory=uow_factory)
