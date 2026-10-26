"""FastAPI dependency providers for the contributions module.

Scope: saved contribution plans and their confirmation.
"""

from __future__ import annotations

from fastapi import Depends

from fincontrol_api.composition import get_uow_factory
from fincontrol_api.core.deps import UoWFactory
from fincontrol_api.modules.contributions.use_cases import ContributionHandler
from fincontrol_api.modules.portfolio.dependencies import get_portfolio_service
from fincontrol_api.modules.portfolio.service import PortfolioApplicationService


def get_contribution_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> ContributionHandler:
    """Provide the ContributionHandler instance."""
    return ContributionHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)
