"""HTTP controllers (routers) of the simulation module; they only delegate to use cases."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from controllers.simulation.dependencies import get_simulation_handler
from controllers.simulation.responses import CoverageReportDTO
from domain.simulation.services.use_cases import SimulationHandler

simulation_router = APIRouter(prefix="/simulations", tags=["Simulation"])


@simulation_router.get("/coverage", response_model=CoverageReportDTO)
def get_coverage(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    handler: SimulationHandler = Depends(get_simulation_handler),
) -> CoverageReportDTO:
    return handler.coverage(start=start, end=end)
