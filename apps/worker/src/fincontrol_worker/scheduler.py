"""APScheduler entrypoint for background market sync, quote warming, and daily snapshots."""

from __future__ import annotations

import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler
from fincontrol_core.market.bcb import BcbSgsProvider
from fincontrol_core.market.brapi import BrapiProvider
from fincontrol_core.market.cache import build_cache_backend
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.market.yfinance_provider import YFinanceProvider
from fincontrol_persistence.unit_of_work import SqlAlchemyUnitOfWork

from fincontrol_worker.jobs import (
    record_daily_snapshot_job,
    sync_bcb_and_benchmarks_job,
    warm_portfolio_quotes_job,
)

logger = logging.getLogger("fincontrol_worker")


def build_worker_gateway() -> CachedMarketGateway:
    """Construct CachedMarketGateway from environment variables."""
    redis_url = os.getenv("REDIS_URL")
    brapi_token = os.getenv("BRAPI_TOKEN")
    cdi_default = float(os.getenv("DEFAULT_CDI_ANNUAL_RATE", "0.1075"))
    ipca_default = float(os.getenv("DEFAULT_IPCA_ANNUAL_RATE", "0.045"))
    return CachedMarketGateway(
        brapi=BrapiProvider(token=brapi_token),
        yfinance=YFinanceProvider(),
        bcb=BcbSgsProvider(default_cdi_annual=cdi_default, default_ipca_annual=ipca_default),
        cache=build_cache_backend(redis_url),
    )


def create_scheduler(gateway: CachedMarketGateway | None = None) -> BlockingScheduler:
    """Create and configure the APScheduler BlockingScheduler with all recurring jobs."""
    gw = gateway or build_worker_gateway()
    scheduler = BlockingScheduler(timezone="America/Sao_Paulo")

    quote_interval_min = int(os.getenv("WORKER_QUOTE_INTERVAL_MINUTES", "15"))

    scheduler.add_job(
        warm_portfolio_quotes_job,
        trigger="interval",
        minutes=quote_interval_min,
        kwargs={"uow_factory": SqlAlchemyUnitOfWork, "gateway": gw},
        id="warm_portfolio_quotes",
        replace_existing=True,
    )
    scheduler.add_job(
        sync_bcb_and_benchmarks_job,
        trigger="cron",
        hour=19,
        minute=0,
        kwargs={"uow_factory": SqlAlchemyUnitOfWork, "gateway": gw},
        id="sync_bcb_and_benchmarks",
        replace_existing=True,
    )
    scheduler.add_job(
        record_daily_snapshot_job,
        trigger="cron",
        hour=19,
        minute=30,
        kwargs={"uow_factory": SqlAlchemyUnitOfWork, "gateway": gw},
        id="record_daily_snapshot",
        replace_existing=True,
    )
    return scheduler


def main() -> None:
    """Start the background worker process."""
    logging.basicConfig(level=logging.INFO)
    gateway = build_worker_gateway()
    logger.info("Running initial market series sync and daily snapshot...")
    try:
        sync_bcb_and_benchmarks_job(SqlAlchemyUnitOfWork, gateway)
        record_daily_snapshot_job(SqlAlchemyUnitOfWork, gateway)
    except Exception as exc:
        logger.warning("Initial sync warning: %s", exc)

    scheduler = create_scheduler(gateway)
    logger.info("Starting APScheduler worker loop...")
    scheduler.start()


if __name__ == "__main__":
    main()
