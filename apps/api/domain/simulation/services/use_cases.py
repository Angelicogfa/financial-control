"""Use cases (query/command handlers) for the simulation module (Phase 33)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

from controllers.shared.dependencies import UoWFactory
from controllers.simulation.requests import BacktestRequest
from controllers.simulation.responses import (
    CoverageReportDTO,
    SeriesCoverageDTO,
    SimulationResultDTO,
    SimulationRunDetailDTO,
    SimulationRunDTO,
)
from core.errors import NotFoundError, ValidationError
from domain.simulation.data import (
    SIMULATION_HISTORY_START,
    coverage_report,
    simulation_universe,
)
from domain.simulation.entities import SimulationResult, SimulationRun
from domain.simulation.runs import BacktestParams, Universe, new_backtest_run


def to_run_dto(run: SimulationRun) -> SimulationRunDTO:
    return SimulationRunDTO(**asdict(run))


def to_result_dto(result: SimulationResult) -> SimulationResultDTO:
    return SimulationResultDTO(
        key=result.key,
        label=result.label,
        summary=result.summary,  # type: ignore[arg-type]
        points=result.points,  # type: ignore[arg-type]
        unavailable=result.extra.get("unavailable", []),
        survivorship_bias=bool(result.extra.get("survivorship_bias", False)),
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

    def submit_backtest(
        self, req: BacktestRequest, *, today: date | None = None
    ) -> SimulationRunDTO:
        """Queue a backtest (PENDING); the worker executes it and stores the results."""
        if req.start >= req.end:
            raise ValidationError("start must be before end", code="INVALID_PERIOD")
        if req.end > (today or date.today()):
            raise ValidationError("end cannot be in the future", code="INVALID_PERIOD")
        with_catalog = req.universe == Universe.REGISTERED_AND_CATALOG
        params = BacktestParams(
            start=req.start,
            end=req.end,
            monthly_contribution=req.monthly_contribution,
            initial_contribution=req.initial_contribution,
            correct_by_ipca=req.correct_by_ipca,
            fee_rate=req.fee_rate,
            rebalance=req.rebalance,
            universe=req.universe,
            catalog_top=(req.catalog_top if req.catalog_top is not None else self.catalog_top)
            if with_catalog
            else 0,
            policy_mode=req.policy_mode,
            benchmarks=tuple(dict.fromkeys(req.benchmarks)),
        )
        with self.uow_factory() as uow:
            run = uow.simulations.add(new_backtest_run(params, label=req.label))
            uow.commit()
        return to_run_dto(run)

    def get_run(self, run_id: int) -> SimulationRunDetailDTO:
        with self.uow_factory() as uow:
            run = uow.simulations.get(run_id)
            if run is None:
                raise NotFoundError(f"Simulation run {run_id} not found")
            results = uow.simulations.results(run_id)
        return SimulationRunDetailDTO(
            **to_run_dto(run).model_dump(), results=[to_result_dto(r) for r in results]
        )

    def list_runs(self, limit: int = 20) -> list[SimulationRunDTO]:
        with self.uow_factory() as uow:
            return [to_run_dto(r) for r in uow.simulations.list_recent(limit)]
