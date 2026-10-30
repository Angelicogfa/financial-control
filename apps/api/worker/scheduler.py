"""APScheduler entrypoint for background market sync, quote warming, and daily snapshots."""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import partial
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler

from core.logging import configure_logging
from core.settings import Settings, get_settings
from domain.market.services.use_cases import MANUAL_JOBS
from infra.data.unit_of_work import SqlAlchemyUnitOfWork
from infra.providers.factory import build_market_gateway
from infra.providers.gateway import CachedMarketGateway
from worker.jobs import (
    UoWFactory,
    backfill_and_record_snapshot_job,
    backfill_snapshots_job,
    calibrate_forecasts_job,
    ensure_series_coverage_job,
    estimate_forecast_models_job,
    has_pending_simulations,
    record_checklist_evaluations_job,
    record_daily_snapshot_job,
    refresh_asset_forecasts_job,
    refresh_catalog_fundamentals_job,
    refresh_distributions_job,
    refresh_fundamentals_job,
    refresh_watchlist_quotes_job,
    run_pending_simulations_job,
    sync_bcb_and_benchmarks_job,
    sync_cvm_documents_job,
    sync_cvm_statements_job,
    sync_instrument_catalog_job,
    sync_mining_universe_job,
    sync_price_history_job,
    sync_simulation_history_job,
    sync_treasury_catalog_job,
    sync_treasury_prices_job,
    warm_portfolio_quotes_job,
)
from worker.runner import JobLock, RetryPolicy, build_job_lock, run_job, run_requested

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


def manual_jobs(cfg: Settings) -> dict[str, Callable[[UoWFactory, CachedMarketGateway], Any]]:
    """The jobs of `MANUAL_JOBS`, each taking (uow_factory, gateway) like the scheduled ones."""
    jobs: dict[str, Callable[[UoWFactory, CachedMarketGateway], Any]] = {
        "sync_simulation_history": partial(
            sync_simulation_history_job, catalog_top=cfg.simulation_catalog_top
        ),
        "sync_cvm_documents": sync_cvm_documents_job,
        "sync_cvm_statements": sync_cvm_statements_job,
        "warm_portfolio_quotes": partial(
            warm_portfolio_quotes_job, max_workers=cfg.market_fetch_workers
        ),
        "sync_price_history": partial(sync_price_history_job, max_workers=cfg.market_fetch_workers),
        "refresh_distributions": partial(
            refresh_distributions_job, max_workers=cfg.market_fetch_workers
        ),
        "refresh_catalog_fundamentals": partial(
            refresh_catalog_fundamentals_job, max_workers=cfg.market_fetch_workers
        ),
        "refresh_asset_forecasts": partial(
            refresh_asset_forecasts_job, catalog_top=cfg.simulation_catalog_top
        ),
        "calibrate_forecasts": partial(
            calibrate_forecasts_job, catalog_top=cfg.simulation_catalog_top
        ),
        "estimate_forecast_models": partial(
            estimate_forecast_models_job, catalog_top=cfg.simulation_catalog_top
        ),
        "sync_mining_universe": partial(
            sync_mining_universe_job,
            min_daily_volume=cfg.mining_min_daily_volume,
            batch=cfg.mining_history_batch,
        ),
    }
    return {name: jobs[name] for name in MANUAL_JOBS}


def _when_pending(uow_factory: UoWFactory, job: Callable[[], Any]) -> Callable[[], Any]:
    """Run `job` only when a simulation is queued, so idle polls leave no job_runs rows."""

    def tick() -> Any:
        if has_pending_simulations(uow_factory):
            return job()
        return None

    return tick


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
        guard(
            "warm_portfolio_quotes",
            partial(warm_portfolio_quotes_job, max_workers=cfg.market_fetch_workers),
        ),
        trigger="interval",
        minutes=cfg.quote_refresh_minutes,
        id="warm_portfolio_quotes",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard(
            "refresh_watchlist_quotes",
            partial(refresh_watchlist_quotes_job, max_workers=cfg.market_fetch_workers),
        ),
        trigger="interval",
        minutes=cfg.watchlist_refresh_minutes,
        id="refresh_watchlist_quotes",
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
    # Ledger changes delete the snapshots from their date on; refill them between runs.
    scheduler.add_job(
        guard("backfill_snapshots", backfill_snapshots_job),
        trigger="interval",
        minutes=cfg.quote_refresh_minutes,
        id="backfill_snapshots",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard("record_daily_snapshot", backfill_and_record_snapshot_job),
        trigger="cron",
        day_of_week="mon-fri",
        hour=cfg.snapshot_cron_hour,
        minute=cfg.snapshot_cron_minute,
        id="record_daily_snapshot",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard("sync_instrument_catalog", sync_instrument_catalog_job),
        trigger="cron",
        day_of_week="mon-fri",
        hour=cfg.catalog_sync_cron_hour,
        minute=0,
        id="sync_instrument_catalog",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard(
            "sync_price_history",
            partial(sync_price_history_job, max_workers=cfg.market_fetch_workers),
        ),
        trigger="cron",
        day_of_week="mon-fri",
        hour=cfg.catalog_sync_cron_hour,
        minute=30,
        id="sync_price_history",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard(
            "refresh_catalog_fundamentals",
            partial(refresh_catalog_fundamentals_job, max_workers=cfg.market_fetch_workers),
        ),
        trigger="cron",
        day_of_week="mon-fri",
        hour=(cfg.catalog_sync_cron_hour + 1) % 24,
        minute=0,
        id="refresh_catalog_fundamentals",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard(
            "refresh_asset_forecasts",
            partial(refresh_asset_forecasts_job, catalog_top=cfg.simulation_catalog_top),
        ),
        trigger="cron",
        day_of_week="mon-fri",
        hour=(cfg.catalog_sync_cron_hour + 2) % 24,
        minute=0,
        id="refresh_asset_forecasts",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard(
            "calibrate_forecasts",
            partial(calibrate_forecasts_job, catalog_top=cfg.simulation_catalog_top),
        ),
        trigger="cron",
        day_of_week=cfg.fundamentals_cron_day_of_week,
        hour=(cfg.fundamentals_cron_hour + 1) % 24,
        minute=0,
        id="calibrate_forecasts",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard(
            "estimate_forecast_models",
            partial(estimate_forecast_models_job, catalog_top=cfg.simulation_catalog_top),
        ),
        trigger="cron",
        day_of_week=cfg.fundamentals_cron_day_of_week,
        hour=(cfg.fundamentals_cron_hour + 2) % 24,
        minute=0,
        id="estimate_forecast_models",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard(
            "sync_mining_universe",
            partial(
                sync_mining_universe_job,
                min_daily_volume=cfg.mining_min_daily_volume,
                batch=cfg.mining_history_batch,
            ),
        ),
        trigger="cron",
        day_of_week="mon-fri",
        hour=(cfg.catalog_sync_cron_hour + 3) % 24,
        minute=0,
        id="sync_mining_universe",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard(
            "refresh_distributions",
            partial(refresh_distributions_job, max_workers=cfg.market_fetch_workers),
        ),
        trigger="interval",
        hours=cfg.distributions_refresh_hours,
        id="refresh_distributions",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard("sync_cvm_documents", sync_cvm_documents_job),
        trigger="cron",
        hour=cfg.cvm_sync_cron_hour,
        minute=10,
        id="sync_cvm_documents",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard("sync_cvm_statements", sync_cvm_statements_job),
        trigger="cron",
        hour=(cfg.cvm_sync_cron_hour + 1) % 24,
        minute=10,
        id="sync_cvm_statements",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard("sync_treasury_catalog", sync_treasury_catalog_job),
        trigger="cron",
        day_of_week="mon-fri",
        hour=cfg.catalog_sync_cron_hour,
        minute=10,
        id="sync_treasury_catalog",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        guard("sync_treasury_prices", sync_treasury_prices_job),
        trigger="cron",
        day_of_week="mon-fri",
        hour=cfg.catalog_sync_cron_hour,
        minute=20,
        id="sync_treasury_prices",
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
    scheduler.add_job(
        guard(
            "sync_simulation_history",
            partial(sync_simulation_history_job, catalog_top=cfg.simulation_catalog_top),
        ),
        trigger="cron",
        day_of_week=cfg.fundamentals_cron_day_of_week,
        hour=cfg.fundamentals_cron_hour,
        minute=50,
        id="sync_simulation_history",
        replace_existing=True,
        **defaults,
    )
    scheduler.add_job(
        _when_pending(
            uow_factory,
            guard(
                "run_pending_simulations",
                partial(
                    run_pending_simulations_job, timeout_seconds=cfg.simulation_timeout_seconds
                ),
            ),
        ),
        trigger="interval",
        seconds=cfg.simulation_poll_seconds,
        id="run_pending_simulations",
        replace_existing=True,
        **defaults,
    )
    # Manual requests (Market data screen, MCP): served on the same short interval; an idle
    # check leaves no job_runs row, and the scheduled run of the same job shares its lock.
    for name, job in manual_jobs(cfg).items():
        scheduler.add_job(
            partial(
                run_requested,
                name,
                partial(job, uow_factory, gw),
                uow_factory=uow_factory,
                lock=job_lock,
                policy=policy,
            ),
            trigger="interval",
            seconds=cfg.simulation_poll_seconds,
            id=f"manual_{name}",
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
    """Store the holdings quotes and bring series and snapshots up to date before the schedule."""
    job_lock = lock or build_job_lock(settings.redis_url)
    policy = RetryPolicy(
        settings.job_max_retries, settings.job_retry_backoff_seconds, settings.job_lock_ttl_seconds
    )
    for name, job in (
        # First, so the screens have stored quotes as soon as the worker is up (Phase 38).
        (
            "warm_portfolio_quotes",
            partial(warm_portfolio_quotes_job, max_workers=settings.market_fetch_workers),
        ),
        ("sync_bcb_and_benchmarks", sync_bcb_and_benchmarks_job),
        (
            "refresh_distributions",
            partial(refresh_distributions_job, max_workers=settings.market_fetch_workers),
        ),
        (
            "sync_price_history",
            partial(sync_price_history_job, max_workers=settings.market_fetch_workers),
        ),
        ("sync_treasury_catalog", sync_treasury_catalog_job),
        ("sync_treasury_prices", sync_treasury_prices_job),
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
