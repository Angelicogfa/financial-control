"""FastAPI dependency providers for the tax module.

Scope: tax rule registry, per-asset tax status and the fixed income comparator.
"""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from controllers.portfolio.dependencies import get_portfolio_service
from controllers.shared.dependencies import UoWFactory
from domain.portfolio.services.service import PortfolioApplicationService
from domain.tax.services.use_cases import TaxHandler


def get_tax_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> TaxHandler:
    """Provide the TaxHandler instance."""
    return TaxHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)
