"""HTTP controllers (routers) of the simulation module; they only delegate to use cases."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, status

from controllers.simulation.dependencies import get_simulation_handler
from controllers.simulation.requests import BacktestRequest, CandidatesRequest, ProjectionRequest
from controllers.simulation.responses import (
    CalibrationDTO,
    CandidatesDTO,
    CoverageReportDTO,
    ProjectionDTO,
    RobustnessDTO,
    SimulationRunDetailDTO,
    SimulationRunDTO,
)
from domain.simulation.entities import SimulationKind
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


@simulation_router.post(
    "/projections", response_model=SimulationRunDTO, status_code=status.HTTP_202_ACCEPTED
)
def submit_projection(
    req: ProjectionRequest,
    handler: SimulationHandler = Depends(get_simulation_handler),
) -> SimulationRunDTO:
    return handler.submit_projection(req)


@simulation_router.post(
    "/candidates", response_model=SimulationRunDTO, status_code=status.HTTP_202_ACCEPTED
)
def submit_candidates(
    req: CandidatesRequest,
    handler: SimulationHandler = Depends(get_simulation_handler),
) -> SimulationRunDTO:
    return handler.submit_candidates(req)


@simulation_router.get("/{run_id}/candidates", response_model=CandidatesDTO)
def get_candidates(
    run_id: int,
    handler: SimulationHandler = Depends(get_simulation_handler),
) -> CandidatesDTO:
    return handler.candidates(run_id)


@simulation_router.post(
    "/calibrations", response_model=SimulationRunDTO, status_code=status.HTTP_202_ACCEPTED
)
def submit_calibration(
    handler: SimulationHandler = Depends(get_simulation_handler),
) -> SimulationRunDTO:
    return handler.submit_calibration()


@simulation_router.get("/calibration", response_model=CalibrationDTO)
def get_calibration(
    run_id: int | None = Query(default=None),
    handler: SimulationHandler = Depends(get_simulation_handler),
) -> CalibrationDTO:
    return handler.calibration(run_id)


@simulation_router.get("", response_model=list[SimulationRunDTO])
def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    kind: SimulationKind | None = Query(default=None),
    handler: SimulationHandler = Depends(get_simulation_handler),
) -> list[SimulationRunDTO]:
    return handler.list_runs(limit, kind)


@simulation_router.get("/{run_id}/projection", response_model=ProjectionDTO)
def get_projection(
    run_id: int,
    handler: SimulationHandler = Depends(get_simulation_handler),
) -> ProjectionDTO:
    return handler.projection(run_id)


@simulation_router.get("/{run_id}/robustness", response_model=RobustnessDTO)
def get_robustness(
    run_id: int,
    handler: SimulationHandler = Depends(get_simulation_handler),
) -> RobustnessDTO:
    return handler.robustness(run_id)


@simulation_router.get("/{run_id}", response_model=SimulationRunDetailDTO)
def get_run(
    run_id: int,
    handler: SimulationHandler = Depends(get_simulation_handler),
) -> SimulationRunDetailDTO:
    return handler.get_run(run_id)
