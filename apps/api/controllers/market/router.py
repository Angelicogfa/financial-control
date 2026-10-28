"""HTTP controllers (routers) of the market module; they only delegate to use cases.

Scope: market data jobs and series freshness.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from controllers.market.dependencies import get_market_data_handler
from controllers.market.responses import (
    JobRunDTO,
    SeriesStatusDTO,
    WorkerErrorsResponseDTO,
)
from domain.market.services.use_cases import MarketDataHandler

market_router = APIRouter(prefix="/market", tags=["Market Data"])


@market_router.get("/job-runs", response_model=list[JobRunDTO])
def get_job_runs(
    handler: MarketDataHandler = Depends(get_market_data_handler),
) -> list[JobRunDTO]:
    return handler.job_runs()


@market_router.post(
    "/job-runs/{job_name}/request",
    response_model=JobRunDTO,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_job(
    job_name: str,
    handler: MarketDataHandler = Depends(get_market_data_handler),
) -> JobRunDTO:
    """Ask the worker to run a job now (only the jobs allowed to run by hand)."""
    return handler.request_job(job_name)


@market_router.get("/series-status", response_model=list[SeriesStatusDTO])
def get_series_status(
    handler: MarketDataHandler = Depends(get_market_data_handler),
) -> list[SeriesStatusDTO]:
    return handler.series_status()


@market_router.get("/worker-errors", response_model=WorkerErrorsResponseDTO)
def get_worker_errors(
    include_resolved: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    handler: MarketDataHandler = Depends(get_market_data_handler),
) -> WorkerErrorsResponseDTO:
    return handler.worker_errors(include_resolved=include_resolved, limit=limit)


@market_router.delete("/worker-errors/{error_id}", status_code=status.HTTP_204_NO_CONTENT)
def resolve_worker_error(
    error_id: int,
    handler: MarketDataHandler = Depends(get_market_data_handler),
) -> Response:
    handler.resolve_worker_error(error_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@market_router.delete("/worker-errors", status_code=status.HTTP_204_NO_CONTENT)
def resolve_all_worker_errors(
    handler: MarketDataHandler = Depends(get_market_data_handler),
) -> Response:
    handler.resolve_all_worker_errors()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
