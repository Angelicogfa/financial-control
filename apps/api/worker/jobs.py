"""Background worker jobs using UnitOfWork and CachedMarketGateway."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from core.helpers.calendar import business_days_between, is_business_day
from core.helpers.units import BCB_SERIES_UNITS
from domain.assets.services.cerrado import (
    answer_freshness,
    evaluate,
    evaluation_record,
    history_for_assets,
    record_if_changed,
)
from domain.assets.services.history import STATEMENT_TYPES
from domain.disclosures.services.statements_sync import sync_statements
from domain.disclosures.services.sync import sync_documents
from domain.forecast.runs import (
    estimate_valuation_model,
    refresh_forecasts,
    run_calibration,
)
from domain.market.entities import Quote, QuoteFreshness
from domain.market.services.treasury_prices import (
    RATE_SUFFIX,
    asset_family,
    asset_price_symbol,
    bond_family,
    price_symbol,
)
from domain.mining.runs import run_mining
from domain.mining.universe import mining_universe
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
from domain.simulation.data import (
    FX_USDBRL,
    INDEX_SOURCES,
    SIMULATION_HISTORY_START,
    index_symbol,
    px_symbol,
    simulation_universe,
    split_symbol,
    tr_symbol,
)
from domain.simulation.runs import execute_next_run, queue_calibration
from infra.providers.batch import fetch_distributions, fetch_histories, fetch_market_data
from infra.providers.gateway import CachedMarketGateway
from infra.providers.stored import (
    refresh_stored_market_data,
    refresh_stored_usd_brl,
    stored_macro_rates,
    stored_usd_brl,
)

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


# Fundamentals change slowly: the quote jobs ask for them again only after this age.
FUNDAMENTALS_MAX_AGE = timedelta(hours=24)


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _refresh_market_data(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    holdings: bool,
    max_workers: int,
    timeout_seconds: float,
    now: datetime | None = None,
) -> int:
    """Store fresh quotes (and stale fundamentals) of the holdings or of the watchlist."""
    at = now or datetime.now(UTC)
    with uow_factory() as uow:
        traded = uow.transactions.traded_asset_ids()
        assets = [
            a
            for a in uow.assets.list_all(active_only=True)
            if a.market not in (Market.MANUAL, Market.FIXED_INCOME_CURVE)
            and (a.id in traded) == holdings
        ]
        stored = uow.market_data.get_many(a.ticker for a in assets)
        stale = [
            a
            for a in assets
            if (data := stored.get(a.ticker)) is None
            or data.fundamentals_fetched_at is None
            or _as_utc(data.fundamentals_fetched_at) < at - FUNDAMENTALS_MAX_AGE
        ]
        fetched = refresh_stored_market_data(
            uow,
            gateway,
            quotes_for=assets,
            fundamentals_for=stale,
            max_workers=max_workers,
            timeout_seconds=timeout_seconds,
            now=at,
        )
        if holdings:
            refresh_stored_usd_brl(uow, gateway, now=at)
        uow.commit()
    return len(fetched.quotes)


def warm_portfolio_quotes_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    max_workers: int = 8,
    timeout_seconds: float = 300.0,
    now: datetime | None = None,
) -> int:
    """Store the quotes of the assets with trades; the screens read them from the database."""
    return _refresh_market_data(
        uow_factory,
        gateway,
        holdings=True,
        max_workers=max_workers,
        timeout_seconds=timeout_seconds,
        now=now,
    )


def refresh_watchlist_quotes_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    max_workers: int = 8,
    timeout_seconds: float = 900.0,
    now: datetime | None = None,
) -> int:
    """Store the quotes of the followed assets without trades, on a slower cadence."""
    return _refresh_market_data(
        uow_factory,
        gateway,
        holdings=False,
        max_workers=max_workers,
        timeout_seconds=timeout_seconds,
        now=now,
    )


# Asset types whose declared distributions the B3 publishes (the Home earnings agenda).
DISTRIBUTION_TYPES = frozenset({AssetType.STOCK_BR, AssetType.BDR, AssetType.FII})
# A stored history older than this is loaded again in full instead of extended.
HISTORY_GAP = timedelta(days=25)


def _market_assets(uow: AbstractUnitOfWork) -> list[AssetEntity]:
    return [
        a
        for a in uow.assets.list_all(active_only=True)
        if a.market not in (Market.MANUAL, Market.FIXED_INCOME_CURVE)
    ]


def sync_price_history_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    max_workers: int = 8,
    timeout_seconds: float = 900.0,
    now: datetime | None = None,
) -> dict[str, int]:
    """Store the daily closes of the active assets (Phase 39.2).

    A ticker loaded for the first time (or after a long gap) gets its whole history; the others
    get the last month, which also corrects late adjustments of the provider.
    """
    at = now or datetime.now(UTC)
    with uow_factory() as uow:
        assets = _market_assets(uow)
        stored = uow.market_data.get_many(a.ticker for a in assets)
        last = uow.price_history.last_dates(a.ticker for a in assets)
        full = [
            a
            for a in assets
            if (data := stored.get(a.ticker)) is None
            or data.history_loaded_at is None
            or a.ticker not in last
            or last[a.ticker] < at.date() - HISTORY_GAP
        ]
        full_tickers = {a.ticker for a in full}
        recent = [a for a in assets if a.ticker not in full_tickers]
        loaded = fetch_histories(
            gateway,
            full,
            range_period="max",
            max_workers=max_workers,
            timeout_seconds=timeout_seconds,
            bypass_cache=True,
        )
        extended = fetch_histories(
            gateway,
            recent,
            range_period="1mo",
            max_workers=max_workers,
            timeout_seconds=timeout_seconds,
            bypass_cache=True,
        )
        for ticker, points in {**loaded, **extended}.items():
            uow.price_history.upsert(ticker, points, fetched_at=at)
        uow.market_data.mark_history_loaded(loaded, loaded_at=at)
        uow.commit()
    return {"full": len(loaded), "recent": len(extended)}


def refresh_distributions_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    max_workers: int = 8,
    timeout_seconds: float = 600.0,
    now: datetime | None = None,
) -> int:
    """Store the declared distributions of the B3 assets (Phase 39.3).

    An empty answer replaces nothing already stored: a provider that is down would otherwise
    wipe the agenda; an old declaration left behind is harmless, the agenda filters by date.
    """
    at = now or datetime.now(UTC)
    with uow_factory() as uow:
        assets = [a for a in _market_assets(uow) if a.asset_type in DISTRIBUTION_TYPES]
        stored = uow.market_data.get_many(a.ticker for a in assets)
        found = fetch_distributions(
            gateway,
            assets,
            max_workers=max_workers,
            timeout_seconds=timeout_seconds,
            bypass_cache=True,
        )
        kept = {
            ticker: value
            for ticker, value in found.items()
            if value.cash
            or value.stock
            or (data := stored.get(ticker)) is None
            or data.distributions is None
        }
        uow.market_data.save_distributions(kept, fetched_at=at)
        uow.commit()
    return len(kept)


def refresh_catalog_fundamentals_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    max_workers: int = 8,
    timeout_seconds: float = 3000.0,
    now: datetime | None = None,
) -> int:
    """Store the indicators of the B3 catalog read by the screener (Phase 39.5)."""
    at = now or datetime.now(UTC)
    with uow_factory() as uow:
        probes = [
            AssetEntity(ticker=i.ticker, name=i.name, asset_type=i.asset_type)
            for i in uow.catalog.list_all()
            if i.asset_type is not None
        ]
        stored = uow.market_data.get_many(p.ticker for p in probes)
        stale = [
            p
            for p in probes
            if (data := stored.get(p.ticker)) is None
            or data.fundamentals_fetched_at is None
            or _as_utc(data.fundamentals_fetched_at) < at - FUNDAMENTALS_MAX_AGE
        ]
        fetched = refresh_stored_market_data(
            uow,
            gateway,
            quotes_for=(),
            fundamentals_for=stale,
            max_workers=max_workers,
            timeout_seconds=timeout_seconds,
            now=at,
        )
        uow.commit()
    return len(fetched.fundamentals)


def refresh_asset_forecasts_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    catalog_top: int = 0,
    now: datetime | None = None,
) -> dict[str, int]:
    """Compute and store the price forecast of every registered asset (Phase 42.1)."""
    at = now or datetime.now(UTC)
    with uow_factory() as uow:
        cdi, _ipca = stored_macro_rates(uow, gateway, today=at.date())
        projections = current_policy(uow.policies).valuation.projections
        if projections.projected_cdi_rate is not None:
            cdi = projections.projected_cdi_rate
        counts = refresh_forecasts(
            uow,
            cdi_annual=cdi,
            usd_brl=stored_usd_brl(uow, gateway),
            catalog_top=catalog_top,
            today=at.date(),
        )
        uow.commit()
    return counts


def estimate_forecast_models_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    catalog_top: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Estimate layer B (valuation) of the forecast, with its out-of-sample gate (42.3)."""
    at = now or datetime.now(UTC)
    with uow_factory() as uow:
        result = estimate_valuation_model(uow, catalog_top=catalog_top, today=at.date())
        uow.commit()
    if result is None:
        return {"companies": 0}
    return {
        "companies": result["companies"],
        "months": result["months"],
        "passed": result["passed"],
        "oos_improvement": result["oos_improvement"],
    }


def calibrate_forecasts_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    catalog_top: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Score the past forecasts (rolling origin) and store the calibration (Phase 42.1)."""
    at = now or datetime.now(UTC)
    with uow_factory() as uow:
        result = run_calibration(uow, catalog_top=catalog_top, today=at.date())
        uow.commit()
    return result or {"windows": 0}


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


TREASURY_HISTORY_LOOKBACK = timedelta(days=365)
# The daily catalog adds one point a day; a longer hole means the history must be refetched.
TREASURY_GAP_TOLERANCE = timedelta(days=5)


def sync_treasury_prices_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    today: date | None = None,
) -> dict[str, int]:
    """Store the daily redemption price and rate of every held Tesouro bond (Phase 26.1).

    Bonds without history (or with a hole) get it from the Tesouro Transparente price file,
    from one year before the first purchase; then the stored daily catalog adds today's point.
    """
    reference = today or date.today()
    with uow_factory() as uow:
        assets = [a for a in uow.assets.list_all(active_only=True) if asset_price_symbol(a)]
        catalog = uow.treasury_catalog.list_all()
        targets: dict[str, tuple[str, date]] = {}
        for asset in assets:
            symbol = asset_price_symbol(asset) or ""
            first = min((t.trade_date for t in asset.transactions), default=reference)
            previous = targets.get(symbol)
            targets[symbol] = (
                asset_family(asset) or "",
                min(first, previous[1]) if previous else first,
            )
        coverage = {symbol: uow.market_series.date_range(symbol) for symbol in targets}
    if not targets:
        return {}

    # Refetch when there is no series, it starts after the first purchase or has a hole at
    # the end; the fetch starts one year before the first purchase for context.
    stale = {
        symbol: first - TREASURY_HISTORY_LOOKBACK
        for symbol, (_family, first) in targets.items()
        if coverage[symbol] is None
        or coverage[symbol][0] > first
        or reference - coverage[symbol][1] > TREASURY_GAP_TOLERANCE
    }
    prices: dict[str, list[tuple[date, float]]] = {s: [] for s in targets}
    rates: dict[str, list[tuple[date, float]]] = {s: [] for s in targets}
    if stale:
        history = gateway.get_treasury_price_history(
            families={targets[s][0] for s in stale}, since=min(stale.values())
        )
        for point in history:
            symbol = price_symbol(bond_family(point.bond_type), point.maturity_date)
            if symbol not in stale or point.base_date < stale[symbol]:
                continue
            if point.sell_price is not None:
                prices[symbol].append((point.base_date, point.sell_price))
            if point.sell_rate is not None:
                rates[symbol].append((point.base_date, point.sell_rate))

    for bond in catalog:
        symbol = price_symbol(bond_family(bond.bond_type), bond.maturity_date)
        if symbol not in targets or bond.base_date is None:
            continue
        if bond.sell_price is not None:
            prices[symbol].append((bond.base_date, bond.sell_price))
        if bond.sell_rate is not None:
            rates[symbol].append((bond.base_date, bond.sell_rate))

    stored: dict[str, int] = {}
    with uow_factory() as uow:
        for symbol in targets:
            stored[symbol] = uow.market_series.upsert_points(
                symbol, sorted(dict(prices[symbol]).items()), unit=SeriesUnit.PRICE
            )
            uow.market_series.upsert_points(
                f"{symbol}:{RATE_SUFFIX}",
                sorted(dict(rates[symbol]).items()),
                unit=SeriesUnit.PERCENT_PER_YEAR,
            )
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
        eligibility = current_policy(uow.policies).eligibility
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
                freshness=answer_freshness(
                    eligibility, now.date(), snapshots.get(asset.ticker, [])
                ),
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


def sync_cvm_documents_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    as_of_date: date | None = None,
) -> dict[str, object]:
    """Load the CVM disclosures of the held and followed companies (Phase 28.3).

    Provider failures are captured by the job runner into the worker error log (Phase 19).
    """
    result = sync_documents(
        uow_factory,
        fetch_tickers=gateway.get_cvm_issuer_tickers,
        fetch_documents=gateway.get_cvm_documents,
        today=as_of_date,
    )
    logger.info("CVM disclosures synced", extra={"job": "sync_cvm_documents", "new": result.new})
    return result.as_details()


def sync_cvm_statements_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    as_of_date: date | None = None,
    max_files: int = 4,
    timeout_seconds: float = 1500.0,
) -> dict[str, object]:
    """Load the DFP/ITR statements of the listed companies, point in time (Phase 42.2).

    The last two years are checked every run; the history since 2010 comes a few files a run.
    """
    started = time.monotonic()
    result = sync_statements(
        uow_factory,
        fetch_stamp=gateway.get_cvm_statement_stamp,
        fetch_statements=gateway.get_cvm_statements,
        today=as_of_date,
        max_files=max_files,
        deadline=lambda: time.monotonic() - started > timeout_seconds,
    )
    logger.info(
        "CVM statements synced", extra={"job": "sync_cvm_statements", "facts": result.facts}
    )
    return result.as_details()


def store_long_history(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    ticker: str,
    asset_type: AssetType | None,
    *,
    start: date,
    end: date,
) -> int:
    """Reload a ticker's long history in full: total return, split-adjusted price and splits.

    Always in full from `start`: Yahoo rescales the whole dividend-adjusted series after every
    new dividend, so appending would mix scales.
    """
    points = gateway.get_full_history(ticker, asset_type=asset_type, start=start)
    if not points:
        return 0
    with uow_factory() as uow:
        count = uow.market_series.upsert_points(
            tr_symbol(ticker),
            [(p.date, p.adj_close or p.close) for p in points if p.date <= end],
            unit=SeriesUnit.PRICE,
        )
        uow.market_series.upsert_points(
            px_symbol(ticker),
            [(p.date, p.close) for p in points if p.date <= end],
            unit=SeriesUnit.PRICE,
        )
        splits = [(p.date, p.split) for p in points if p.split and p.date <= end]
        if splits:  # Yahoo's prices are split-adjusted; the valuation undoes it (42.3)
            uow.market_series.upsert_points(split_symbol(ticker), splits, unit=SeriesUnit.RATIO)
        uow.commit()
    return count


MINING_HISTORY_MAX_AGE_DAYS = 7


def sync_mining_universe_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    as_of_date: date | None = None,
    min_daily_volume: float = 1_000_000.0,
    batch: int = 60,
    start: date = SIMULATION_HISTORY_START,
    timeout_seconds: float = 1500.0,
) -> dict[str, object]:
    """Long histories of the mining universe (Phase 43.1), the stalest first, `batch` a run.

    A history counts as fresh when its last stored day is less than a week old; the weekly
    reload keeps the dividend-adjusted series on one scale.
    """
    end = as_of_date or date.today()
    started = time.monotonic()
    with uow_factory() as uow:
        members = mining_universe(uow, min_daily_volume)
        last = {m.ticker: uow.market_series.date_range(px_symbol(m.ticker)) for m in members}
    stale = [
        m
        for m in members
        if last[m.ticker] is None or (end - last[m.ticker][1]).days >= MINING_HISTORY_MAX_AGE_DAYS  # type: ignore[index]
    ]
    stale.sort(key=lambda m: last[m.ticker][1] if last[m.ticker] else date.min)  # type: ignore[index]
    loaded: list[str] = []
    empty: list[str] = []
    for member in stale[:batch]:
        if time.monotonic() - started > timeout_seconds:
            break
        count = store_long_history(
            uow_factory, gateway, member.ticker, AssetType.STOCK_BR, start=start, end=end
        )
        (loaded if count else empty).append(member.ticker)
    return {
        "universe": len(members),
        "fresh": len(members) - len(stale),
        "loaded": len(loaded),
        "without_history": empty[:20],
        "remaining": max(len(stale) - len(loaded) - len(empty), 0),
    }


def run_mining_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    min_daily_volume: float = 1_000_000.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The weekly Garimpo: signals, gated model, findings and record (Phases 43.2-43.5)."""
    at = now or datetime.now(UTC)
    with uow_factory() as uow:
        result = run_mining(uow, min_daily_volume=min_daily_volume, today=at.date())
        uow.commit()
    last = result.get("last_month")
    return {**result, "last_month": last.isoformat() if last else None}


def sync_simulation_history_job(
    uow_factory: UoWFactory,
    gateway: CachedMarketGateway,
    *,
    as_of_date: date | None = None,
    catalog_top: int = 50,
    start: date = SIMULATION_HISTORY_START,
) -> dict[str, int]:
    """Store the long histories the simulation reads (Phase 33.1).

    Asset histories are always reloaded in full from `start`: Yahoo rescales the whole
    dividend-adjusted series after every new dividend, so appending would mix scales. CDI is
    completed back to `start` incrementally (BCB values do not change).
    """
    end = as_of_date or date.today()
    with uow_factory() as uow:
        universe = simulation_universe(uow, catalog_top)
        cdi_range = uow.market_series.date_range("CDI")

    counts: dict[str, int] = {}
    for asset in universe:
        counts[asset.ticker] = store_long_history(
            uow_factory, gateway, asset.ticker, asset.asset_type, start=start, end=end
        )

    for label, yahoo_symbol in INDEX_SOURCES.items():
        points = gateway.get_full_history(yahoo_symbol, market=Market.INDEX, start=start)
        with uow_factory() as uow:
            counts[label] = uow.market_series.upsert_points(
                index_symbol(label),
                [(p.date, p.adj_close or p.close) for p in points if p.date <= end],
                unit=SeriesUnit.INDEX_POINTS,
            )
            uow.commit()

    fx = gateway.get_full_history(USD_BRL_SYMBOL, market=Market.INDEX, start=start)
    with uow_factory() as uow:
        counts["USDBRL"] = uow.market_series.upsert_points(
            FX_USDBRL, [(p.date, p.close) for p in fx if p.date <= end], unit=SeriesUnit.PRICE
        )
        counts["CDI"] = 0
        for window_start, window_end in _missing_windows(cdi_range, start, end, full=False):
            points = gateway.fetch_bcb_series("CDI", start_date=window_start, end_date=window_end)
            counts["CDI"] += uow.market_series.upsert_points(
                "CDI",
                [(p.reference_date, p.value) for p in points],
                unit=BCB_SERIES_UNITS["CDI"],
            )
        # Fresh history: recalibrate the scenario generators (Phase 33.6, decision 10).
        counts["calibration_run"] = queue_calibration(uow).id or 0
        uow.commit()
    logger.info("Simulation history synced", extra={"job": "sync_simulation_history"})
    return counts


def run_pending_simulations_job(
    uow_factory: UoWFactory,
    _gateway: CachedMarketGateway | None = None,
    *,
    timeout_seconds: float = 120.0,
    max_runs: int = 5,
) -> dict[str, int]:
    """Execute queued simulation runs, oldest first (Phase 33.3).

    Each run has its own time limit; a failing or timed-out run is stored as such and the
    next one still runs.
    """
    counts: dict[str, int] = {}
    for _ in range(max_runs):
        run = execute_next_run(uow_factory, timeout_seconds=timeout_seconds)
        if run is None:
            break
        counts[run.status.value] = counts.get(run.status.value, 0) + 1
        logger.info(
            "Simulation run %s finished with %s",
            run.id,
            run.status.value,
            extra={"job": "run_pending_simulations"},
        )
    return counts


def has_pending_simulations(uow_factory: UoWFactory) -> bool:
    with uow_factory() as uow:
        return uow.simulations.next_pending() is not None
