"""Use cases (command/query handlers) for the market module.

Scope: market data jobs and series freshness.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from controllers.market.responses import (
    JobRunDTO,
    SeriesStatusDTO,
    WorkerErrorsResponseDTO,
    WorkerRequestErrorDTO,
)
from controllers.shared.dependencies import UoWFactory
from core.errors import NotFoundError
from domain.market.services.series_status import TRACKED_SERIES, evaluate_series_status


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

    def worker_errors(
        self, *, include_resolved: bool = False, limit: int = 100
    ) -> WorkerErrorsResponseDTO:
        """List recent worker request errors and the count of unresolved notifications."""
        with self.uow_factory() as uow:
            items = uow.worker_errors.list_recent(include_resolved=include_resolved, limit=limit)
            unresolved_count = uow.worker_errors.count_unresolved()
            return WorkerErrorsResponseDTO(
                unresolved_count=unresolved_count,
                errors=[
                    WorkerRequestErrorDTO(
                        id=item.id or 0,
                        job_run_id=item.job_run_id,
                        job_name=item.job_name,
                        provider=item.provider,
                        operation=item.operation,
                        target=item.target,
                        request_url=item.request_url,
                        status_code=item.status_code,
                        error_type=item.error_type,
                        error_detail=item.error_detail,
                        occurred_at=item.occurred_at,
                        resolved_at=item.resolved_at,
                    )
                    for item in items
                ],
            )

    def resolve_worker_error(self, error_id: int) -> None:
        """Mark a single worker request error notification as resolved."""
        now = datetime.now(UTC)
        with self.uow_factory() as uow:
            if not uow.worker_errors.resolve(error_id, now):
                raise NotFoundError(f"Worker request error id={error_id} not found")
            uow.commit()

    def resolve_all_worker_errors(self) -> int:
        """Mark all unresolved worker request error notifications as resolved."""
        now = datetime.now(UTC)
        with self.uow_factory() as uow:
            count = uow.worker_errors.resolve_all(now)
            uow.commit()
            return count
