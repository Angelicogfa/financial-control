"""Use cases (query/command handlers) for the simulation module (Phase 33)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

from controllers.shared.dependencies import UoWFactory
from controllers.simulation.responses import CoverageReportDTO, SeriesCoverageDTO
from core.errors import ValidationError
from domain.simulation.data import (
    SIMULATION_HISTORY_START,
    coverage_report,
    simulation_universe,
)


class SimulationHandler:
    """Application handler for the portfolio simulation."""

    def __init__(self, uow_factory: UoWFactory, *, catalog_top: int = 50) -> None:
        self.uow_factory = uow_factory
        self.catalog_top = catalog_top

    def coverage(self, *, start: date | None = None, end: date | None = None) -> CoverageReportDTO:
        """Coverage of the stored series a simulation over the universe would read."""
        first = start or SIMULATION_HISTORY_START
        last = end or date.today()
        if first >= last:
            raise ValidationError("start must be before end", code="INVALID_PERIOD")
        with self.uow_factory() as uow:
            tickers = [a.ticker for a in simulation_universe(uow, self.catalog_top)]
            report = coverage_report(uow.market_series, tickers, start=first, end=last)
        return CoverageReportDTO(
            start=report.start,
            end=report.end,
            series=[SeriesCoverageDTO(**asdict(s), share=round(s.share, 4)) for s in report.series],
            missing=report.missing,
        )
