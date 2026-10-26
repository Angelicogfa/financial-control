"""FastAPI dependency providers for the contributions module.

Scope: saved contribution plans and their confirmation.
"""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from controllers.portfolio.dependencies import get_portfolio_service
from controllers.shared.dependencies import UoWFactory
from domain.contributions.services.use_cases import ContributionHandler
from domain.portfolio.services.service import PortfolioApplicationService


def get_contribution_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> ContributionHandler:
    """Provide the ContributionHandler instance."""
    return ContributionHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)
