"""Market data read from the database, refreshed by the worker (Phase 38).

Screens read the last quote and fundamentals the worker saved (`market_data`) instead of
calling the providers, so the response time no longer depends on how many assets are
registered or on a provider being slow. Only a ticker never stored (an asset registered a
moment ago) is fetched live, and only that one.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime

from domain.market.entities import Fundamentals, QuoteFreshness
from domain.shared.entities import AssetEntity
from domain.shared.enums import Market
from domain.shared.unit_of_work import AbstractUnitOfWork
from infra.providers.batch import OFFLINE_MARKETS, MarketSnapshot, fetch_market_data
from infra.providers.gateway import CachedMarketGateway

# The USD/BRL rate is stored like a quote, under its provider symbol.
FX_SYMBOL = "USDBRL=X"


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
) -> MarketSnapshot:
    """Quotes and fundamentals of the assets from the database, live only for what is missing."""
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

    # A ticker the worker already refreshed is never fetched here, even when a provider had
    # no fundamentals for it: only the ones never stored (just registered) go live.
    never_stored = [a for a in tradable if a.ticker not in stored]
    if never_stored:
        live = fetch_market_data(
            gateway,
            never_stored,
            include_quotes=include_quotes,
            include_fundamentals=include_fundamentals,
            max_workers=max_workers,
            timeout_seconds=timeout_seconds,
        )
        result.quotes.update({t: q for t, q in live.quotes.items() if t not in result.quotes})
        result.fundamentals.update(
            {t: f for t, f in live.fundamentals.items() if t not in result.fundamentals}
        )
        result.timed_out = live.timed_out
    return result


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
