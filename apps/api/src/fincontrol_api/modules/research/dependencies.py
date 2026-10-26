"""FastAPI dependency providers for the research module.

Scope: B3 catalog screener and watchlist.
"""

from __future__ import annotations

from fastapi import Depends
from fincontrol_core.market.gateway import CachedMarketGateway

from fincontrol_api.composition import get_market_gateway, get_uow_factory
from fincontrol_api.core.deps import UoWFactory
from fincontrol_api.modules.portfolio.dependencies import get_portfolio_service
from fincontrol_api.modules.portfolio.service import PortfolioApplicationService
from fincontrol_api.modules.research.service import StatementRefresher
from fincontrol_api.modules.research.use_cases import ResearchHandler


def get_research_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> ResearchHandler:
    """Provide the ResearchHandler instance."""
    return ResearchHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)


def get_statement_refresher(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    gateway: CachedMarketGateway = Depends(get_market_gateway),
) -> StatementRefresher:
    """Provide the StatementRefresher that fetches statements of newly researched assets."""
    return StatementRefresher(uow_factory=uow_factory, gateway=gateway)
