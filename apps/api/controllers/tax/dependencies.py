"""FastAPI dependency providers for the tax module.

Scope: tax rule registry, per-asset tax status and the fixed income comparator.
"""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from controllers.portfolio.dependencies import get_portfolio_service
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.unit_of_work import UoWFactory
from domain.tax.services.monthly import MonthlyTaxHandler
from domain.tax.services.use_cases import TaxHandler


def get_tax_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> TaxHandler:
    """Provide the TaxHandler instance."""
    return TaxHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)


def get_monthly_tax_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> MonthlyTaxHandler:
    """Provide the MonthlyTaxHandler instance (Phase 48.R7)."""
    return MonthlyTaxHandler(uow_factory=uow_factory)
