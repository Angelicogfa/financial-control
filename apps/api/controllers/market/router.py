"""HTTP controllers (routers) of the market module; they only delegate to use cases.

Scope: market data jobs and series freshness.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from controllers.market.dependencies import get_market_data_handler
from controllers.market.responses import JobRunDTO, SeriesStatusDTO
from domain.market.services.use_cases import MarketDataHandler

market_router = APIRouter(prefix="/market", tags=["Market Data"])


@market_router.get("/job-runs", response_model=list[JobRunDTO])
def get_job_runs(
    handler: MarketDataHandler = Depends(get_market_data_handler),
) -> list[JobRunDTO]:
    return handler.job_runs()


@market_router.get("/series-status", response_model=list[SeriesStatusDTO])
def get_series_status(
    handler: MarketDataHandler = Depends(get_market_data_handler),
) -> list[SeriesStatusDTO]:
    return handler.series_status()
