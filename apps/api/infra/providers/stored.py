"""Market data read from the database, refreshed by the worker (Phase 38).

Screens read what the worker saved instead of calling the providers, so the response time no
longer depends on how many assets are registered or on a provider being slow:

- `market_data`: last quote, fundamentals and declared distributions of each ticker;
- `asset_price_history`: daily closes (Phase 39.2);
- `market_series`: the BCB series behind the annual CDI and IPCA (Phase 39.4).

Only a ticker never stored (an asset registered a moment ago, a ticker typed in the
comparator) is fetched live: at most `MAX_LIVE_FETCH` per request, never for an archived
asset, and stored when the caller commits (`persist=True`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

from domain.market.entities import (
    AnnouncedDistributions,
    Fundamentals,
    PricePoint,
    QuoteFreshness,
)
from domain.market.services.macro import annual_cdi_rate, annual_ipca_rate
from domain.shared.entities import AssetEntity
from domain.shared.enums import AssetType, Market
from domain.shared.unit_of_work import AbstractUnitOfWork
from infra.providers.batch import (
    OFFLINE_MARKETS,
    MarketSnapshot,
    fetch_distributions,
    fetch_histories,
    fetch_market_data,
)
from infra.providers.gateway import CachedMarketGateway

# The USD/BRL rate is stored like a quote, under its provider symbol.
FX_SYMBOL = "USDBRL=X"

# A request never asks the providers for more tickers than this, whatever is missing.
MAX_LIVE_FETCH = 25

# Provider range -> days of history a screen asks for (None: the whole stored history).
RANGE_DAYS: dict[str, int | None] = {
    "5d": 7,
    "1mo": 31,
    "3mo": 92,
    "6mo": 183,
    "1y": 366,
    "2y": 731,
    "5y": 1827,
    "10y": 3653,
    "max": None,
}


def _live_candidates(assets: Iterable[AssetEntity]) -> list[AssetEntity]:
    """Assets that may be fetched live: active ones, at most `MAX_LIVE_FETCH`."""
    return [a for a in assets if a.is_active][:MAX_LIVE_FETCH]


def range_start(range_period: str, today: date | None = None) -> date | None:
    days = RANGE_DAYS.get(range_period, 366)
    return None if days is None else (today or date.today()) - timedelta(days=days)


def stored_macro_rates(
    uow: AbstractUnitOfWork, gateway: CachedMarketGateway, *, today: date | None = None
) -> tuple[float, float]:
    """(annual CDI, annual IPCA) from the stored BCB series; the gateway only without them."""
    as_of = today or date.today()
    cdi = annual_cdi_rate(
        uow.market_series.list_series("CDI", date_from=as_of - timedelta(days=30), date_to=as_of)
    )
    ipca = annual_ipca_rate(
        uow.market_series.list_series("IPCA", date_from=as_of - timedelta(days=400), date_to=as_of)
    )
    if cdi is None or ipca is None:
        live_cdi, live_ipca = gateway.get_macro_rates()
        return (live_cdi if cdi is None else cdi, live_ipca if ipca is None else ipca)
    return cdi, ipca


def stored_usd_brl(uow: AbstractUnitOfWork, gateway: CachedMarketGateway) -> float:
    """The stored USD/BRL rate; the gateway (cache or provider) only before the first refresh."""
    data = uow.market_data.get_many([FX_SYMBOL]).get(FX_SYMBOL)
    if data is not None and data.quote is not None and data.quote.price > 0:
        return data.quote.price
    return gateway.get_usd_brl_rate()


def refresh_stored_usd_brl(
    uow: AbstractUnitOfWork, gateway: CachedMarketGateway, *, now: datetime | None = None
) -> bool:
    """Ask the provider for USD/BRL and store it; a failure keeps the last rate."""
    quote = gateway.get_quote(FX_SYMBOL, market=Market.INDEX, bypass_cache=True)
    if quote is None or quote.price <= 0:
        return False
    uow.market_data.save_quotes({FX_SYMBOL: quote}, fetched_at=now or datetime.now(UTC))
    return True


def stored_fundamentals(
    uow: AbstractUnitOfWork, gateway: CachedMarketGateway, asset: AssetEntity
) -> Fundamentals | None:
    """Stored fundamentals of one asset (live only if it was never stored)."""
    return stored_market_data(uow, gateway, [asset], include_quotes=False).fundamentals.get(
        asset.ticker
    )


def stored_market_data(
    uow: AbstractUnitOfWork,
    gateway: CachedMarketGateway,
    assets: Iterable[AssetEntity],
    *,
    include_quotes: bool = True,
    include_fundamentals: bool = True,
    max_workers: int = 8,
    timeout_seconds: float = 20.0,
    persist: bool = False,
) -> MarketSnapshot:
    """Quotes and fundamentals of the assets from the database, live only for what is missing.

    `persist` saves what was fetched live (the caller commits).
    """
    tradable = [a for a in assets if a.market not in OFFLINE_MARKETS]
    result = MarketSnapshot()
    if not tradable:
        return result
    stored = uow.market_data.get_many(a.ticker for a in tradable)
    for ticker, data in stored.items():
        if include_quotes and data.quote is not None:
            quote = data.quote
            if quote.freshness != QuoteFreshness.FALLBACK:
                quote = replace(quote, freshness=QuoteFreshness.CACHED)
            result.quotes[ticker] = quote
        if include_fundamentals and data.fundamentals is not None:
            result.fundamentals[ticker] = data.fundamentals

    # Each part goes live only when nothing was ever stored for it: a row holding just the
    # indicators the screener saved still needs its first quote. The gateway remembers a
    # provider miss for a few minutes, so a ticker the provider has no data for stays cheap.
    budget = MAX_LIVE_FETCH
    for quotes in (True, False):
        wanted = include_quotes if quotes else include_fundamentals
        have = result.quotes if quotes else result.fundamentals
        missing = _live_candidates(a for a in tradable if wanted and a.ticker not in have)[:budget]
        if not missing:
            continue
        budget -= len(missing)
        live = fetch_market_data(
            gateway,
            missing,
            include_quotes=quotes,
            include_fundamentals=not quotes,
            max_workers=max_workers,
            timeout_seconds=timeout_seconds,
        )
        result.quotes.update(live.quotes)
        result.fundamentals.update(live.fundamentals)
        result.timed_out += live.timed_out
        if persist:
            at = datetime.now(UTC)
            uow.market_data.save_quotes(live.quotes, fetched_at=at)
            uow.market_data.save_fundamentals(live.fundamentals, fetched_at=at)
    return result


def stored_distributions(
    uow: AbstractUnitOfWork,
    gateway: CachedMarketGateway,
    assets: Iterable[AssetEntity],
    *,
    max_workers: int = 8,
    timeout_seconds: float = 20.0,
) -> dict[str, AnnouncedDistributions]:
    """Declared distributions from the database (Phase 39.3), live only for never-stored ones."""
    tradable = [a for a in assets if a.market not in OFFLINE_MARKETS]
    stored = uow.market_data.get_many(a.ticker for a in tradable)
    found = {t: d.distributions for t, d in stored.items() if d.distributions is not None}
    missing = _live_candidates(a for a in tradable if a.ticker not in found)
    if missing:
        found.update(
            fetch_distributions(
                gateway, missing, max_workers=max_workers, timeout_seconds=timeout_seconds
            )
        )
    return found


def distribution_lookup(
    uow_factory: Callable[[], AbstractUnitOfWork], gateway: CachedMarketGateway
) -> Callable[..., AnnouncedDistributions]:
    """`(ticker, asset_type)` -> declared distributions, stored first (B3 import, MCP)."""

    def lookup(ticker: str, asset_type: AssetType | None = None) -> AnnouncedDistributions:
        with uow_factory() as uow:
            data = uow.market_data.get_many([ticker]).get(ticker.strip().upper())
        if data is not None and data.distributions is not None:
            return data.distributions
        return gateway.get_distributions(ticker, asset_type=asset_type)

    return lookup


def stored_histories(
    uow: AbstractUnitOfWork,
    gateway: CachedMarketGateway,
    assets: Iterable[AssetEntity],
    *,
    range_period: str = "2y",
    max_workers: int = 8,
    timeout_seconds: float = 20.0,
    persist: bool = False,
    today: date | None = None,
) -> dict[str, list[PricePoint]]:
    """Daily closes of the period from the database (Phase 39.2).

    A ticker with no stored day at all is fetched live (and saved with `persist`); one whose
    stored days are all older than the period has none in it.
    """
    tradable = [a for a in assets if a.market not in OFFLINE_MARKETS]
    if not tradable:
        return {}
    tickers = [a.ticker for a in tradable]
    found = uow.price_history.list_for_many(tickers, date_from=range_start(range_period, today))
    known = uow.price_history.last_dates(tickers)
    missing = _live_candidates(a for a in tradable if a.ticker not in known)
    if missing:
        live = fetch_histories(
            gateway,
            missing,
            range_period=range_period,
            max_workers=max_workers,
            timeout_seconds=timeout_seconds,
        )
        found.update(live)
        if persist:
            at = datetime.now(UTC)
            for ticker, points in live.items():
                uow.price_history.upsert(ticker, points, fetched_at=at)
    return found


def stored_history(
    uow: AbstractUnitOfWork,
    gateway: CachedMarketGateway,
    asset: AssetEntity,
    range_period: str,
) -> list[PricePoint]:
    """Daily closes of one asset for the period, from the database."""
    return stored_histories(uow, gateway, [asset], range_period=range_period).get(asset.ticker, [])


def refresh_stored_market_data(
    uow: AbstractUnitOfWork,
    gateway: CachedMarketGateway,
    *,
    quotes_for: Iterable[AssetEntity],
    fundamentals_for: Iterable[AssetEntity] = (),
    max_workers: int = 8,
    timeout_seconds: float = 300.0,
    now: datetime | None = None,
) -> MarketSnapshot:
    """Ask the providers again and save what arrived; a ticker that failed keeps its last value."""
    at = now or datetime.now(UTC)
    result = MarketSnapshot()
    for assets, quotes in ((list(quotes_for), True), (list(fundamentals_for), False)):
        if not assets:
            continue
        fetched = fetch_market_data(
            gateway,
            assets,
            include_quotes=quotes,
            include_fundamentals=not quotes,
            max_workers=max_workers,
            timeout_seconds=timeout_seconds,
            bypass_cache=True,
        )
        result.quotes.update(fetched.quotes)
        result.fundamentals.update(fetched.fundamentals)
        result.timed_out += fetched.timed_out
    uow.market_data.save_quotes(result.quotes, fetched_at=at)
    uow.market_data.save_fundamentals(result.fundamentals, fetched_at=at)
    return result
