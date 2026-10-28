"""HTTP controllers (routers) of the simulation module; they only delegate to use cases."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, status

from controllers.simulation.dependencies import get_simulation_handler
from controllers.simulation.requests import BacktestRequest
from controllers.simulation.responses import (
    CoverageReportDTO,
    SimulationRunDetailDTO,
    SimulationRunDTO,
)
from domain.simulation.services.use_cases import SimulationHandler

simulation_router = APIRouter(prefix="/simulations", tags=["Simulation"])


@simulation_router.get("/coverage", response_model=CoverageReportDTO)
def get_coverage(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    handler: SimulationHandler = Depends(get_simulation_handler),
) -> CoverageReportDTO:
    return handler.coverage(start=start, end=end)


@simulation_router.post(
    "/backtests", response_model=SimulationRunDTO, status_code=status.HTTP_202_ACCEPTED
)
def submit_backtest(
    req: BacktestRequest,
    handler: SimulationHandler = Depends(get_simulation_handler),
) -> SimulationRunDTO:
    return handler.submit_backtest(req)


@simulation_router.get("", response_model=list[SimulationRunDTO])
def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    handler: SimulationHandler = Depends(get_simulation_handler),
) -> list[SimulationRunDTO]:
    return handler.list_runs(limit)


@simulation_router.get("/{run_id}", response_model=SimulationRunDetailDTO)
def get_run(
    run_id: int,
    handler: SimulationHandler = Depends(get_simulation_handler),
) -> SimulationRunDetailDTO:
    return handler.get_run(run_id)
