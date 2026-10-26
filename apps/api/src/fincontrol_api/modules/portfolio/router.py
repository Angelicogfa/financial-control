"""HTTP controllers (routers) of the portfolio module; they only delegate to use cases.

Scope: consolidated portfolio, ARCA allocation, snapshots and analytics.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from fincontrol_api.modules.portfolio.dependencies import get_portfolio_handler
from fincontrol_api.modules.portfolio.schemas import (
    ContributionPlanResponseDTO,
    ContributionSimulationRequest,
    PortfolioAnalyticsResponseDTO,
    PortfolioReportResponseDTO,
    SnapshotPointDTO,
)
from fincontrol_api.modules.portfolio.use_cases import PortfolioHandler

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
