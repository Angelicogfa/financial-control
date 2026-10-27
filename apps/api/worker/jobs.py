"""Background worker jobs using UnitOfWork and CachedMarketGateway."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from core.helpers.calendar import business_days_between, is_business_day
from core.helpers.units import BCB_SERIES_UNITS
from domain.assets.services.cerrado import (
    evaluate,
    evaluation_record,
    history_for_assets,
    record_if_changed,
)
from domain.assets.services.history import STATEMENT_TYPES
from domain.market.entities import Quote, QuoteFreshness
from domain.policy.services.allocation import ArcaTargets
from domain.policy.services.policy import EligibilityPolicy, current_policy
from domain.portfolio.services.consolidation import consolidate_portfolio
from domain.portfolio.services.curves import earliest_fixed_income_start, load_rate_curves
from domain.portfolio.services.fixed_income import RateCurves
from domain.portfolio.services.snapshots import (
    PriceLookup,
    first_trade_date,
    history_range_for,
    history_start,
    invalid_ledger_tickers,
    net_flow_between,
    snapshot_from_report,
)
from domain.portfolio.services.treasury_rates import IPCA_HISTORY_START
from domain.shared.entities import AssetEntity, PortfolioSnapshotEntity
from domain.shared.enums import (
    ArcaClass,
    AssetType,
    IntraClassStrategy,
    Market,
    SeriesUnit,
)
from domain.shared.unit_of_work import AbstractUnitOfWork
from infra.providers.batch import fetch_market_data
from infra.providers.gateway import CachedMarketGateway

UoWFactory = Callable[[], AbstractUnitOfWork]

logger = logging.getLogger("fincontrol_worker")

BCB_SYMBOLS = ("CDI", "SELIC", "IPCA")
BENCHMARK_TICKERS = {"IBOV": "^BVSP", "IFIX": "IFIX.SA", "SP500": "^GSPC"}
USD_BRL_SYMBOL = "USDBRL=X"
# Weekends/holidays at the start of a window never get a point; do not refetch for them.
COVERAGE_TOLERANCE = timedelta(days=7)


@dataclass(frozen=True)
class _Targets:
    targets: ArcaTargets
    strategies: dict[ArcaClass, IntraClassStrategy]
    bands: dict[ArcaClass, float]
    eligibility: EligibilityPolicy


def _load_targets(uow: AbstractUnitOfWork) -> _Targets:
    policy = current_policy(uow.policies)
    arca = policy.arca
    return _Targets(arca.targets, arca.strategies, arca.bands, policy.eligibility)


def _missing_windows(
    stored: tuple[date, date] | None, start: date, end: date, *, full: bool
) -> list[tuple[date, date]]:
    """Date windows not yet persisted for a series (incremental sync, finding I-03)."""
    if full or stored is None:
        return [(start, end)]
    first, last = stored
    windows: list[tuple[date, date]] = []
    if start < first:
        windows.append((start, first - timedelta(days=1)))
    if last < end:
        windows.append((last + timedelta(days=1), end))
    return windows


def _sync_start(symbol: str, start: date) -> date:
    """First date to keep of a BCB series: IPCA always since July 2000 (Tesouro IPCA+ VNA)."""
    if symbol == "IPCA":
        return min(date(start.year, start.month, 1), IPCA_HISTORY_START)
    return start


def sync_bcb_and_benchmarks_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    as_of_date: date | None = None,
    full: bool = False,
    include_benchmarks: bool = True,
) -> dict[str, int]:
    """Persist BCB series (CDI, SELIC, IPCA) and benchmarks (IBOV, IFIX, SP500).

    The history starts at the oldest fixed income position or trade (capped at ten years;
    IPCA always since July 2000 for the VNA) and only missing windows are fetched unless
    `full` is set.
    """
    end = as_of_date or date.today()
    counts: dict[str, int] = {}

    with uow_factory() as uow:
        assets = uow.assets.list_all(active_only=False)
        start = history_start(end, earliest_fixed_income_start(assets), first_trade_date(assets))

        for symbol in BCB_SYMBOLS:
            counts[symbol] = 0
            sync_start = _sync_start(symbol, start)
            for window_start, window_end in _missing_windows(
                uow.market_series.date_range(symbol), sync_start, end, full=full
            ):
                points = gateway.fetch_bcb_series(
                    symbol, start_date=window_start, end_date=window_end
                )
                counts[symbol] += uow.market_series.upsert_points(
                    symbol,
                    [(p.reference_date, p.value) for p in points],
                    unit=BCB_SERIES_UNITS[symbol],
                )

        for label, yahoo_symbol in BENCHMARK_TICKERS.items() if include_benchmarks else ():
            history = gateway.get_history(
                yahoo_symbol,
                range_period=history_range_for(start, end),
                market=Market.INDEX,
                bypass_cache=True,
            )
            counts[label] = uow.market_series.upsert_points(
                label,
                [(p.date, p.close) for p in history if start <= p.date <= end],
                unit=SeriesUnit.INDEX_POINTS,
            )

        uow.commit()
    return counts


def ensure_series_coverage_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    as_of_date: date | None = None,
) -> dict[str, int]:
    """Back-fill BCB history right after an older position is recorded.

    Cheap check run on the quote interval: when the oldest position starts before the stored
    CDI/SELIC/IPCA history, the missing early window is fetched at once instead of waiting
    for the nightly sync (keeps `curve_coverage` complete).
    """
    end = as_of_date or date.today()
    with uow_factory() as uow:
        assets = uow.assets.list_all(active_only=False)
        start = history_start(end, earliest_fixed_income_start(assets), first_trade_date(assets))
        gaps = [
            symbol
            for symbol in BCB_SYMBOLS
            if (stored := uow.market_series.date_range(symbol)) is not None
            and _sync_start(symbol, start) < stored[0] - COVERAGE_TOLERANCE
        ]
    if not gaps:
        return {}
    return sync_bcb_and_benchmarks_job(
        uow_factory, gateway, as_of_date=end, include_benchmarks=False
    )


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


def refresh_fundamentals_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    extra_tickers: Iterable[str] = (),
) -> dict[str, int]:
    """Store the yearly statement history of every active company (holdings and watchlist)."""
    with uow_factory() as uow:
        assets = uow.assets.list_all(active_only=True)
    targets = {a.ticker: a.asset_type for a in assets if a.asset_type in STATEMENT_TYPES}
    for ticker in extra_tickers:
        targets.setdefault(ticker.strip().upper(), AssetType.STOCK_BR)

    stored: dict[str, int] = {}
    for ticker, asset_type in sorted(targets.items()):
        snapshots = gateway.get_annual_statements(ticker, asset_type=asset_type, bypass_cache=True)
        if not snapshots:
            stored[ticker] = 0
            continue
        with uow_factory() as uow:
            stored[ticker] = uow.fundamentals.upsert(snapshots)
            uow.commit()
    logger.info("Fundamentals refreshed", extra={"job": "refresh_fundamentals"})
    return stored


def sync_instrument_catalog_job(uow_factory: UoWFactory, gateway: CachedMarketGateway) -> int:
    """Refresh the B3 instrument catalog; keeps the previous one when the source fails."""
    instruments = gateway.list_instruments()
    if not instruments:
        logger.warning("Instrument catalog source returned nothing; keeping the stored catalog")
        return 0
    with uow_factory() as uow:
        stored = uow.catalog.upsert(instruments)
        uow.commit()
    return stored


def sync_treasury_catalog_job(uow_factory: UoWFactory, gateway: CachedMarketGateway) -> int:
    """Refresh the Tesouro Direto catalog; keeps the previous one when the source fails."""
    outcome = gateway.list_treasury_bonds(bypass_cache=True)
    if not outcome.results:
        logger.warning(
            "Treasury catalog source returned nothing (%s); keeping the stored catalog",
            outcome.unavailable_reason or "empty",
        )
        return 0
    with uow_factory() as uow:
        stored = uow.treasury_catalog.upsert(outcome.results)
        uow.commit()
    return stored


def record_checklist_evaluations_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
) -> int:
    """Re-evaluate every active checklist with fresh data; store the changed outcomes."""
    now = datetime.now(UTC)
    recorded = 0
    with uow_factory() as uow:
        assets = [a for a in uow.assets.list_all(active_only=True) if a.id is not None]
        snapshots = uow.fundamentals.list_for_many([a.ticker for a in assets])
        histories = history_for_assets(assets, snapshots)
        for asset in assets:
            fundamentals = (
                None
                if asset.market in (Market.MANUAL, Market.FIXED_INCOME_CURVE)
                else gateway.get_fundamentals(asset.ticker, asset_type=asset.asset_type)
            )
            evaluation = evaluate(
                asset.profile,
                asset.cerrado_answers,
                fundamentals,
                use_cerrado=asset.use_cerrado,
                history=histories.get(asset.ticker),
            )
            if record_if_changed(uow.checklists, evaluation_record(asset.id or 0, evaluation, now)):
                recorded += 1
        uow.commit()
    return recorded


def _rate_curves(
    uow: AbstractUnitOfWork, gateway: CachedMarketGateway, assets: list[AssetEntity], end: date
) -> RateCurves:
    annual_cdi, annual_ipca = gateway.get_macro_rates()
    return load_rate_curves(
        uow.market_series,
        date_from=earliest_fixed_income_start(assets),
        date_to=end,
        annual_cdi_rate=annual_cdi,
        annual_ipca_rate=annual_ipca,
    )


def _snapshot(
    uow: AbstractUnitOfWork,
    assets: list[AssetEntity],
    targets: _Targets,
    *,
    day: date,
    previous: date | None,
    quotes: dict[str, Quote],
    usd_brl: float,
    curves: RateCurves,
    split_adjust_through: date | None = None,
) -> PortfolioSnapshotEntity:
    report = consolidate_portfolio(
        assets=assets,
        targets=targets.targets,
        quotes=quotes,
        intra_strategies=targets.strategies,
        bands=targets.bands,
        eligibility=targets.eligibility,
        usd_brl_rate=usd_brl,
        curves=curves,
        as_of_date=day,
        split_adjust_through=split_adjust_through,
    )
    invalid = invalid_ledger_tickers(report)
    if invalid:
        logger.warning("Snapshot %s excludes invalid ledgers: %s", day, ", ".join(invalid))
    flow = net_flow_between(
        [a for a in assets if a.ticker not in invalid], after=previous, up_to=day
    )
    return uow.snapshots.upsert(snapshot_from_report(report, net_flow=flow))


def record_daily_snapshot_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    snapshot_date: date | None = None,
) -> PortfolioSnapshotEntity | None:
    """Consolidate the portfolio with live quotes and upsert the snapshot of a business day.

    The net flow covers every trade since the previous snapshot, so days the worker was
    down are not lost (finding I-09). Returns None on weekends and holidays.
    """
    ref_date = snapshot_date or date.today()
    if not is_business_day(ref_date):
        return None
    usd_brl = gateway.get_usd_brl_rate()

    with uow_factory() as uow:
        assets = uow.assets.list_all(active_only=True)
        quotes = fetch_market_data(gateway, assets, include_fundamentals=False).quotes

        previous = uow.snapshots.latest_before(ref_date)
        saved = _snapshot(
            uow,
            assets,
            _load_targets(uow),
            day=ref_date,
            previous=previous.snapshot_date if previous else None,
            quotes=quotes,
            usd_brl=usd_brl,
            curves=_rate_curves(uow, gateway, assets, ref_date),
        )
        uow.commit()
        return saved


def _price_history(
    gateway: CachedMarketGateway, assets: Iterable[AssetEntity], start: date, end: date
) -> dict[str, PriceLookup]:
    period = history_range_for(start, end)
    lookups: dict[str, PriceLookup] = {}
    for asset in assets:
        if asset.market in (Market.MANUAL, Market.FIXED_INCOME_CURVE):
            continue
        history = gateway.get_history(
            asset.ticker, range_period=period, asset_type=asset.asset_type
        )
        lookups[asset.ticker] = PriceLookup([(p.date, p.close) for p in history])
    return lookups


def backfill_snapshots_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    end_date: date | None = None,
    overwrite: bool = False,
) -> int:
    """Rebuild missing daily snapshots from the first trade using historical prices (8.9).

    Each business day is valued with the last close on or before it, the historical
    USD/BRL rate and the persisted index curves. Returns the number of snapshots written.
    """
    end = end_date or (date.today() - timedelta(days=1))
    with uow_factory() as uow:
        assets = uow.assets.list_all(active_only=True)
        start = first_trade_date(assets)
        if start is None or start > end:
            return 0
        existing = {s.snapshot_date for s in uow.snapshots.list_range(date_from=start)}
        days = [start] if is_business_day(start) else []
        days += business_days_between(start, end)
        pending = [d for d in days if overwrite or d not in existing]
        if not pending:
            return 0

        prices = _price_history(gateway, assets, start, end)
        fx = PriceLookup(
            [
                (p.date, p.close)
                for p in gateway.get_history(
                    USD_BRL_SYMBOL, range_period=history_range_for(start, end), market=Market.INDEX
                )
            ]
        )
        targets = _load_targets(uow)
        curves = _rate_curves(uow, gateway, assets, end)
        default_fx = gateway.default_usd_brl

        written = 0
        previous: date | None = None
        for day in days:
            if day in pending:
                quotes = {
                    ticker: Quote(symbol=ticker, price=price, freshness=QuoteFreshness.CACHED)
                    for ticker, lookup in prices.items()
                    if (price := lookup.on(day)) is not None
                }
                _snapshot(
                    uow,
                    assets,
                    targets,
                    day=day,
                    previous=previous,
                    quotes=quotes,
                    usd_brl=fx.on(day) or default_fx,
                    curves=curves,
                    # Historical closes are split-adjusted: count shares as of `end`.
                    split_adjust_through=end,
                )
                written += 1
            previous = day
        uow.commit()
    logger.info("Backfilled %d snapshots between %s and %s", written, start, end)
    return written


def backfill_and_record_snapshot_job(
    uow_factory: UoWFactory, gateway: CachedMarketGateway
) -> PortfolioSnapshotEntity | None:
    """Recreate the days a ledger change invalidated, then record today's snapshot.

    Backfilling first keeps today's net flow limited to the trades since yesterday instead
    of also counting the flows of the days still missing.
    """
    backfill_snapshots_job(uow_factory, gateway)
    return record_daily_snapshot_job(uow_factory, gateway)
