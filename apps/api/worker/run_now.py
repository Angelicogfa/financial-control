"""Run a job by hand, now, and wait for it (for jobs that only run on a weekly schedule).

Usage (inside the worker container or with `uv run`):

    python -m worker.run_now sync_simulation_history

The run is locked, retried and recorded in `job_runs` like a scheduled one. To ask the
running worker instead (without waiting), use Settings > Market data or the MCP operation
`market.request_job`.
"""

from __future__ import annotations

import argparse
import json

from core.logging import configure_logging
from core.settings import Settings, get_settings
from domain.market.services.use_cases import MANUAL_JOBS
from domain.shared.enums import JobRunStatus
from infra.data.unit_of_work import SqlAlchemyUnitOfWork
from infra.providers.gateway import CachedMarketGateway
from worker.jobs import UoWFactory
from worker.runner import JobLock, RetryPolicy, build_job_lock, run_job
from worker.scheduler import build_worker_gateway, manual_jobs


def run_now(
    name: str,
    *,
    settings: Settings,
    uow_factory: UoWFactory = SqlAlchemyUnitOfWork,
    gateway: CachedMarketGateway | None = None,
    lock: JobLock | None = None,
) -> int:
    """Run the job and return the process exit code (0 when it succeeded)."""
    job = manual_jobs(settings)[name]
    run = run_job(
        name,
        lambda: job(uow_factory, gateway or build_worker_gateway()),
        uow_factory=uow_factory,
        lock=lock or build_job_lock(settings.redis_url),
        policy=RetryPolicy(
            settings.job_max_retries,
            settings.job_retry_backoff_seconds,
            settings.job_lock_ttl_seconds,
        ),
    )
    print(f"{name}: {run.status.value}")
    if run.details:
        print(json.dumps(run.details, ensure_ascii=False, indent=2, default=str))
    if run.error:
        print(run.error)
    return 0 if run.status == JobRunStatus.SUCCESS else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a worker job now and wait for it.")
    parser.add_argument("job", choices=sorted(MANUAL_JOBS), help="job to run")
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    return run_now(args.job, settings=settings)


if __name__ == "__main__":
    raise SystemExit(main())
