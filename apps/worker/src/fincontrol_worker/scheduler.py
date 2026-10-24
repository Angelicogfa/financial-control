"""APScheduler entrypoint for background market sync, quote warming, and daily snapshots."""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import partial
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from fincontrol_config import Settings, get_settings
from fincontrol_config.logging import configure_logging
from fincontrol_core.market.factory import build_market_gateway
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_persistence.unit_of_work import SqlAlchemyUnitOfWork

from fincontrol_worker.jobs import (
    UoWFactory,
    backfill_snapshots_job,
    ensure_series_coverage_job,
    record_checklist_evaluations_job,
    record_daily_snapshot_job,
    refresh_fundamentals_job,
    sync_bcb_and_benchmarks_job,
    warm_portfolio_quotes_job,
)
from fincontrol_worker.runner import JobLock, RetryPolicy, build_job_lock, run_job

logger = logging.getLogger("fincontrol_worker")


def build_worker_gateway() -> CachedMarketGateway:
    """Construct the market gateway from the shared settings."""
    return build_market_gateway(get_settings())


def _guarded(
    name: str,
    job: Callable[..., Any],
    *,
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    lock: JobLock,
    policy: RetryPolicy,
) -> Callable[[], Any]:
    """Wrap a job so every execution is locked, retried and recorded in job_runs."""
    return partial(
        run_job,
        name,
        partial(job, uow_factory, gateway),
        uow_factory=uow_factory,
        lock=lock,
        policy=policy,
    )


def create_scheduler(
    gateway: CachedMarketGateway | None = None,
    *,
    settings: Settings | None = None,
    uow_factory: UoWFactory = SqlAlchemyUnitOfWork,
    lock: JobLock | None = None,
) -> BlockingScheduler:
    """Create the APScheduler with every recurring job wrapped by `run_job`."""
    cfg = settings or get_settings()
    gw = gateway or build_market_gateway(cfg)
    job_lock = lock or build_job_lock(cfg.redis_url)
    policy = RetryPolicy(
        cfg.job_max_retries, cfg.job_retry_backoff_seconds, cfg.job_lock_ttl_seconds
    )
    guard = partial(_guarded, uow_factory=uow_factory, gateway=gw, lock=job_lock, policy=policy)
    defaults = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600}

    scheduler = BlockingScheduler(timezone=cfg.tz)
    scheduler.add_job(
        guard("warm_portfolio_quotes", warm_portfolio_quotes_job),
        trigger="interval",
        minutes=cfg.quote_refresh_minutes,
        id="warm_portfolio_quotes",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard("ensure_series_coverage", ensure_series_coverage_job),
        trigger="interval",
        minutes=cfg.quote_refresh_minutes,
        id="ensure_series_coverage",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard("sync_bcb_and_benchmarks", sync_bcb_and_benchmarks_job),
        trigger="cron",
        hour=cfg.bcb_sync_cron_hour,
        minute=cfg.bcb_sync_cron_minute,
        id="sync_bcb_and_benchmarks",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard("record_daily_snapshot", record_daily_snapshot_job),
        trigger="cron",
        day_of_week="mon-fri",
        hour=cfg.snapshot_cron_hour,
        minute=cfg.snapshot_cron_minute,
        id="record_daily_snapshot",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard("refresh_fundamentals", refresh_fundamentals_job),
        trigger="cron",
        day_of_week=cfg.fundamentals_cron_day_of_week,
        hour=cfg.fundamentals_cron_hour,
        minute=0,
        id="refresh_fundamentals",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard("record_checklist_evaluations", record_checklist_evaluations_job),
        trigger="cron",
        day_of_week=cfg.fundamentals_cron_day_of_week,
        hour=cfg.fundamentals_cron_hour,
        minute=30,
        id="record_checklist_evaluations",
        replace_existing=True,
        **defaults,
    )
    return scheduler


def run_startup_jobs(
    gateway: CachedMarketGateway,
    *,
    settings: Settings,
    uow_factory: UoWFactory = SqlAlchemyUnitOfWork,
    lock: JobLock | None = None,
) -> None:
    """Bring series and snapshots up to date before the schedule starts."""
    job_lock = lock or build_job_lock(settings.redis_url)
    policy = RetryPolicy(
        settings.job_max_retries, settings.job_retry_backoff_seconds, settings.job_lock_ttl_seconds
    )
    for name, job in (
        ("sync_bcb_and_benchmarks", sync_bcb_and_benchmarks_job),
        ("backfill_snapshots", backfill_snapshots_job),
        ("record_daily_snapshot", record_daily_snapshot_job),
    ):
        _guarded(
            name, job, uow_factory=uow_factory, gateway=gateway, lock=job_lock, policy=policy
        )()


def main() -> None:
    """Start the background worker process."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    gateway = build_market_gateway(settings)
    logger.info("Running startup sync, snapshot backfill and daily snapshot")
    run_startup_jobs(gateway, settings=settings)

    scheduler = create_scheduler(gateway, settings=settings)
    logger.info("Starting APScheduler worker loop")
    scheduler.start()


if __name__ == "__main__":
    main()
