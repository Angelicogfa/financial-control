"""APScheduler entrypoint for background market sync, quote warming, and daily snapshots."""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from fincontrol_config import get_settings
from fincontrol_config.logging import configure_logging
from fincontrol_core.market.factory import build_market_gateway
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_persistence.unit_of_work import SqlAlchemyUnitOfWork

from fincontrol_worker.jobs import (
    backfill_snapshots_job,
    record_daily_snapshot_job,
    sync_bcb_and_benchmarks_job,
    warm_portfolio_quotes_job,
)

logger = logging.getLogger("fincontrol_worker")


def build_worker_gateway() -> CachedMarketGateway:
    """Construct the market gateway from the shared settings."""
    return build_market_gateway(get_settings())


def create_scheduler(gateway: CachedMarketGateway | None = None) -> BlockingScheduler:
    """Create and configure the APScheduler BlockingScheduler with all recurring jobs."""
    gw = gateway or build_worker_gateway()
    settings = get_settings()
    scheduler = BlockingScheduler(timezone=settings.tz)

    scheduler.add_job(
        warm_portfolio_quotes_job,
        trigger="interval",
        minutes=settings.quote_refresh_minutes,
        kwargs={"uow_factory": SqlAlchemyUnitOfWork, "gateway": gw},
        id="warm_portfolio_quotes",
        replace_existing=True,
    )
    scheduler.add_job(
        sync_bcb_and_benchmarks_job,
        trigger="cron",
        hour=settings.bcb_sync_cron_hour,
        minute=settings.bcb_sync_cron_minute,
        kwargs={"uow_factory": SqlAlchemyUnitOfWork, "gateway": gw},
        id="sync_bcb_and_benchmarks",
        replace_existing=True,
    )
    scheduler.add_job(
        record_daily_snapshot_job,
        trigger="cron",
        day_of_week="mon-fri",
        hour=settings.snapshot_cron_hour,
        minute=settings.snapshot_cron_minute,
        kwargs={"uow_factory": SqlAlchemyUnitOfWork, "gateway": gw},
        id="record_daily_snapshot",
        replace_existing=True,
    )
    return scheduler


def main() -> None:
    """Start the background worker process."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    gateway = build_worker_gateway()
    logger.info("Running initial market series sync and daily snapshot...")
    try:
        sync_bcb_and_benchmarks_job(SqlAlchemyUnitOfWork, gateway)
        backfill_snapshots_job(SqlAlchemyUnitOfWork, gateway)
        record_daily_snapshot_job(SqlAlchemyUnitOfWork, gateway)
    except Exception as exc:
        logger.warning("Initial sync warning: %s", exc)

    scheduler = create_scheduler(gateway)
    logger.info("Starting APScheduler worker loop...")
    scheduler.start()


if __name__ == "__main__":
    main()
