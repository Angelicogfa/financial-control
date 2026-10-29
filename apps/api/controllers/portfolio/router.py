"""HTTP controllers (routers) of the portfolio module; they only delegate to use cases.

Scope: consolidated portfolio, ARCA allocation, snapshots and analytics.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from controllers.portfolio.dependencies import get_portfolio_handler
from controllers.portfolio.requests import ContributionSimulationRequest
from controllers.portfolio.responses import (
    ContributionPlanResponseDTO,
    EarningsAgendaDTO,
    PortfolioAnalyticsResponseDTO,
    PortfolioHealthDTO,
    PortfolioReportResponseDTO,
    SnapshotPointDTO,
    TreasuryMarketDTO,
    WealthByAccountDTO,
)
from domain.portfolio.services.use_cases import PortfolioHandler

portfolio_router = APIRouter(prefix="/portfolio", tags=["Portfolio & ARCA"])


@portfolio_router.get("", response_model=PortfolioReportResponseDTO)
def get_portfolio(
    as_of_date: date | None = Query(default=None),
    date_from: date | None = Query(default=None),
    account_id: int | None = Query(default=None),
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> PortfolioReportResponseDTO:
    return handler.get_portfolio_report(
        as_of_date=as_of_date, date_from=date_from, account_id=account_id
    )


@portfolio_router.get("/consolidated", response_model=PortfolioReportResponseDTO)
def get_consolidated_portfolio(
    as_of_date: date | None = Query(default=None),
    date_from: date | None = Query(default=None),
    account_id: int | None = Query(default=None),
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> PortfolioReportResponseDTO:
    return handler.get_portfolio_report(
        as_of_date=as_of_date, date_from=date_from, account_id=account_id
    )


@portfolio_router.get("/by-account", response_model=WealthByAccountDTO)
def get_wealth_by_account(
    as_of_date: date | None = Query(default=None),
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> WealthByAccountDTO:
    """Wealth of each custody account, split into Bolsa and Internacional (Phase 40.2)."""
    return handler.wealth_by_account(as_of_date=as_of_date)


@portfolio_router.post("/contribution", response_model=ContributionPlanResponseDTO)
def simulate_contribution(
    payload: ContributionSimulationRequest,
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> ContributionPlanResponseDTO:
    return handler.simulate_contribution(payload)


@portfolio_router.get("/snapshots", response_model=list[SnapshotPointDTO])
def list_portfolio_snapshots(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> list[SnapshotPointDTO]:
    return handler.list_snapshots(date_from=date_from, date_to=date_to)


@portfolio_router.get("/analytics", response_model=PortfolioAnalyticsResponseDTO)
def get_portfolio_analytics(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> PortfolioAnalyticsResponseDTO:
    return handler.get_analytics(date_from=date_from, date_to=date_to)


@portfolio_router.get("/health", response_model=PortfolioHealthDTO)
def get_portfolio_health(
    as_of_date: date | None = Query(default=None),
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> PortfolioHealthDTO:
    return handler.get_health(as_of_date=as_of_date)


@portfolio_router.get("/treasury-market", response_model=list[TreasuryMarketDTO])
def list_treasury_market(
    as_of_date: date | None = Query(default=None),
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> list[TreasuryMarketDTO]:
    return handler.treasury_market(as_of_date=as_of_date)


@portfolio_router.get("/treasury-market/{asset_id}", response_model=TreasuryMarketDTO)
def get_treasury_market(
    asset_id: int,
    as_of_date: date | None = Query(default=None),
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> TreasuryMarketDTO:
    return handler.treasury_market_detail(asset_id, as_of_date=as_of_date)


@portfolio_router.get("/earnings-agenda", response_model=EarningsAgendaDTO)
def get_earnings_agenda(
    as_of_date: date | None = Query(default=None),
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> EarningsAgendaDTO:
    return handler.earnings_agenda(as_of_date=as_of_date)
