"""Reprocess derived data after the phase 8 engine fixes (item 8.17).

Usage (inside the worker container or with `uv run`):

    python -m fincontrol_worker.rebuild [--skip-fx] [--skip-series] [--skip-snapshots]

Steps:
1. Re-price foreign-currency trades and earnings stored with fx_rate = 1 using the
   historical USD/BRL close of their date (data recorded before FX became mandatory).
2. Re-sync the full BCB and benchmark history.
3. Delete and rebuild every daily snapshot from the first trade, then record today's.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from fincontrol_config import get_settings
from fincontrol_config.logging import configure_logging
from fincontrol_core.domain.enums import Market
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.portfolio.snapshots import PriceLookup, first_trade_date, history_range_for
from fincontrol_persistence.unit_of_work import SqlAlchemyUnitOfWork

from fincontrol_worker.jobs import (
    USD_BRL_SYMBOL,
    UoWFactory,
    backfill_snapshots_job,
    record_daily_snapshot_job,
    sync_bcb_and_benchmarks_job,
)
from fincontrol_worker.scheduler import build_worker_gateway

logger = logging.getLogger("fincontrol_worker.rebuild")

ONE = Decimal("1")


@dataclass
class RebuildReport:
    transactions_repriced: int = 0
    earnings_repriced: int = 0
    unpriced_entries: int = 0
    series_points: int = 0
    snapshots_deleted: int = 0
    snapshots_written: int = 0


def reprice_foreign_entries(
    uow_factory: UoWFactory, gateway: CachedMarketGateway, report: RebuildReport
) -> None:
    """Fill the historical USD/BRL rate on foreign-currency entries saved with fx_rate = 1."""
    with uow_factory() as uow:
        assets = [
            a for a in uow.assets.list_all(active_only=False) if (a.currency or "BRL") != "BRL"
        ]
        start = first_trade_date(assets)
        if start is None:
            return
        fx = PriceLookup(
            [
                (p.date, p.close)
                for p in gateway.get_history(
                    USD_BRL_SYMBOL,
                    range_period=history_range_for(start, date.today()),
                    market=Market.INDEX,
                )
            ]
        )
        for asset in assets:
            for tx in asset.transactions:
                if tx.fx_rate != ONE:
                    continue
                rate = fx.on(tx.trade_date)
                if rate is None:
                    report.unpriced_entries += 1
                    continue
                uow.transactions.update(replace(tx, fx_rate=Decimal(str(round(rate, 6)))))
                report.transactions_repriced += 1
            for earning in asset.earnings:
                if earning.fx_rate != ONE:
                    continue
                rate = fx.on(earning.payment_date)
                if rate is None:
                    report.unpriced_entries += 1
                    continue
                uow.earnings.update(replace(earning, fx_rate=Decimal(str(round(rate, 6)))))
                report.earnings_repriced += 1
        uow.commit()


def rebuild(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    reprice_fx: bool = True,
    resync_series: bool = True,
    rebuild_snapshots: bool = True,
) -> RebuildReport:
    report = RebuildReport()
    if reprice_fx:
        reprice_foreign_entries(uow_factory, gateway, report)
    if resync_series:
        counts = sync_bcb_and_benchmarks_job(uow_factory, gateway, full=True)
        report.series_points = sum(counts.values())
    if rebuild_snapshots:
        with uow_factory() as uow:
            report.snapshots_deleted = uow.snapshots.delete_range()
            uow.commit()
        report.snapshots_written = backfill_snapshots_job(uow_factory, gateway, overwrite=True)
        if record_daily_snapshot_job(uow_factory, gateway) is not None:
            report.snapshots_written += 1
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-fx", action="store_true", help="do not re-price USD entries")
    parser.add_argument("--skip-series", action="store_true", help="do not re-sync BCB series")
    parser.add_argument("--skip-snapshots", action="store_true", help="keep existing snapshots")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    report = rebuild(
        SqlAlchemyUnitOfWork,
        build_worker_gateway(),
        reprice_fx=not args.skip_fx,
        resync_series=not args.skip_series,
        rebuild_snapshots=not args.skip_snapshots,
    )
    logger.info("Rebuild finished: %s", report)


if __name__ == "__main__":
    main()
