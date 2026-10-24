"""Query handler exposing the freshness of persisted market and macro series."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from fincontrol_core.market.series_status import evaluate_series_status
from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork

from fincontrol_api.schemas import JobRunDTO, SeriesStatusDTO

UoWFactory = Callable[[], AbstractUnitOfWork]

TRACKED_SERIES = ("CDI", "SELIC", "IPCA", "IBOV", "IFIX", "SP500")


class MarketDataHandler:
    """Application handler for market data diagnostics."""

    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def series_status(self, today: date | None = None) -> list[SeriesStatusDTO]:
        reference = today or date.today()
        with self.uow_factory() as uow:
            return [
                SeriesStatusDTO(
                    **vars(
                        evaluate_series_status(
                            symbol, uow.market_series.list_series(symbol), reference
                        )
                    )
                )
                for symbol in TRACKED_SERIES
            ]

    def job_runs(self) -> list[JobRunDTO]:
        """Latest execution of each worker job (data freshness indicator)."""
        with self.uow_factory() as uow:
            return [
                JobRunDTO(
                    job_name=run.job_name,
                    status=run.status.value,
                    attempts=run.attempts,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    details=run.details,
                    error=run.error,
                )
                for run in uow.job_runs.latest_per_job()
            ]
