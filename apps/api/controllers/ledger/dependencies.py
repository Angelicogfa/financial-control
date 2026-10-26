"""FastAPI dependency providers for the ledger module.

Scope: transactions, earnings, corporate events and B3 statement imports.
"""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from controllers.portfolio.dependencies import get_portfolio_service
from controllers.shared.dependencies import UoWFactory
from domain.ledger.services.use_cases.b3_import import ImportHandler
from domain.ledger.services.use_cases.corporate_events import CorporateEventHandler
from domain.ledger.services.use_cases.earnings import EarningHandler
from domain.ledger.services.use_cases.transactions import TransactionHandler
from domain.portfolio.services.service import PortfolioApplicationService


def get_import_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> ImportHandler:
    """Provide the ImportHandler instance."""
    return ImportHandler(uow_factory=uow_factory)


def get_event_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> CorporateEventHandler:
    """Provide the CorporateEventHandler instance."""
    return CorporateEventHandler(uow_factory=uow_factory)


def get_transaction_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> TransactionHandler:
    """Provide the TransactionHandler instance."""
    return TransactionHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)


def get_earning_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> EarningHandler:
    """Provide the EarningHandler instance."""
    return EarningHandler(uow_factory=uow_factory)
