"""Background worker jobs using UnitOfWork and CachedMarketGateway."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from fincontrol_core.arca.allocation import ArcaTargets
from fincontrol_core.domain.entities import PortfolioSnapshotEntity
from fincontrol_core.domain.enums import (
    ArcaClass,
    IntraClassStrategy,
    Market,
    SeriesUnit,
    TransactionKind,
)
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.market.units import BCB_SERIES_UNITS
from fincontrol_core.portfolio.consolidation import consolidate_portfolio
from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork

UoWFactory = Callable[[], AbstractUnitOfWork]


def sync_bcb_and_benchmarks_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    as_of_date: date | None = None,
) -> dict[str, int]:
    """Fetch and persist BCB series (CDI, SELIC, IPCA) and benchmarks (IBOV, IFIX, SP500)."""
    end = as_of_date or date.today()
    start = end - timedelta(days=365)
    counts: dict[str, int] = {}

    with uow_factory() as uow:
        for bcb_sym in ("CDI", "SELIC", "IPCA"):
            pts = gateway.fetch_bcb_series(bcb_sym, start_date=start, end_date=end)
            if pts:
                counts[bcb_sym] = uow.market_series.upsert_points(
                    bcb_sym,
                    [(p.reference_date, p.value) for p in pts],
                    unit=BCB_SERIES_UNITS[bcb_sym],
                )
            else:
                counts[bcb_sym] = 0

        benchmark_tickers = {
            "IBOV": "^BVSP",
            "IFIX": "IFIX.SA",
            "SP500": "^GSPC",
        }
        for sym_label, yahoo_sym in benchmark_tickers.items():
            hist = gateway.get_history(
                yahoo_sym, range_period="1y", market=Market.INDEX, bypass_cache=True
            )
            if hist:
                counts[sym_label] = uow.market_series.upsert_points(
                    sym_label,
                    [(p.date, p.close) for p in hist],
                    unit=SeriesUnit.INDEX_POINTS,
                )
            else:
                counts[sym_label] = 0

        uow.commit()
    return counts


def warm_portfolio_quotes_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
) -> int:
    """Refresh cached quotes and fundamentals for all active market-traded assets."""
    with uow_factory() as uow:
        assets = uow.assets.list_all(active_only=True)

    warmed = 0
    for asset in assets:
        if asset.market in (Market.MANUAL, Market.FIXED_INCOME_CURVE):
            continue
        q = gateway.get_quote(asset.ticker, asset_type=asset.asset_type, bypass_cache=True)
        gateway.get_fundamentals(asset.ticker, asset_type=asset.asset_type, bypass_cache=True)
        if q is not None:
            warmed += 1
    return warmed


def record_daily_snapshot_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    snapshot_date: date | None = None,
) -> PortfolioSnapshotEntity:
    """Consolidate portfolio and upsert a daily PortfolioSnapshotEntity via UnitOfWork."""
    ref_date = snapshot_date or date.today()
    usd_brl = gateway.get_usd_brl_rate()
    annual_cdi, annual_ipca = gateway.get_macro_rates()

    with uow_factory() as uow:
        assets = uow.assets.list_all(active_only=True)
        target_rows = uow.arca_targets.get_all()
        if target_rows and len(target_rows) == len(ArcaClass):
            targets = ArcaTargets({r.arca_class: float(r.target_pct) for r in target_rows})
            intra_strategies = {r.arca_class: r.intra_class_strategy for r in target_rows}
        else:
            targets = ArcaTargets.default()
            intra_strategies = {c: IntraClassStrategy.CERRADO for c in ArcaClass}

        quotes = {}
        fundamentals = {}
        net_flow_brl = 0.0

        for asset in assets:
            for tx in asset.transactions:
                if tx.trade_date == ref_date:
                    fx = float(tx.fx_rate) if tx.fx_rate > 0 else 1.0
                    gross_tx = float(tx.quantity * tx.unit_price + tx.fees) * fx
                    net_flow_brl += (
                        gross_tx if tx.kind == TransactionKind.BUY else -gross_tx
                    )

            if asset.market in (Market.MANUAL, Market.FIXED_INCOME_CURVE):
                continue
            q = gateway.get_quote(asset.ticker, asset_type=asset.asset_type)
            if q is not None:
                quotes[asset.ticker] = q
            fund = gateway.get_fundamentals(asset.ticker, asset_type=asset.asset_type)
            if fund is not None:
                fundamentals[asset.ticker] = fund

        cdi_pts = uow.market_series.list_series("CDI", date_to=ref_date)
        daily_cdi_map = {p.reference_date: p.value for p in cdi_pts} if cdi_pts else None

        report = consolidate_portfolio(
            assets=assets,
            targets=targets,
            quotes=quotes,
            fundamentals_by_ticker=fundamentals,
            intra_strategies=intra_strategies,
            usd_brl_rate=usd_brl,
            annual_cdi_rate=annual_cdi,
            annual_ipca_rate=annual_ipca,
            daily_cdi_series=daily_cdi_map,
            as_of_date=ref_date,
        )

        by_class = {
            alloc.arca_class.value: {
                "invested_value": alloc.invested_value,
                "current_value": alloc.current_value,
                "current_pct": alloc.current_pct,
                "target_pct": alloc.target_pct,
            }
            for alloc in report.allocations
        }

        snapshot = PortfolioSnapshotEntity(
            snapshot_date=ref_date,
            invested_value=report.total_invested_brl,
            market_value=report.total_current_value_brl,
            unrealized_pnl=report.total_unrealized_pnl_brl,
            realized_pnl_cum=report.total_realized_pnl_brl,
            earnings_cum=report.total_received_earnings_brl,
            consolidated_pnl=report.total_consolidated_pnl_brl,
            net_flow=round(net_flow_brl, 2),
            by_class=by_class,
        )
        saved = uow.snapshots.upsert(snapshot)
        uow.commit()
        return saved
