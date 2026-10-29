"""Concurrent quote/fundamentals retrieval for a whole portfolio (findings D-05, I-07).

Providers are called in a bounded thread pool with one overall deadline. Assets whose data
does not arrive in time are simply left out, so the valuation falls back to cached/manual
prices instead of blocking the request.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from contextvars import copy_context
from dataclasses import dataclass, field

from domain.market.entities import AnnouncedDistributions, Fundamentals, PricePoint, Quote
from domain.shared.entities import AssetEntity
from domain.shared.enums import Market
from infra.providers.error_tracker import report_provider_error
from infra.providers.gateway import CachedMarketGateway

logger = logging.getLogger("fincontrol_core.market.batch")

OFFLINE_MARKETS = frozenset({Market.MANUAL, Market.FIXED_INCOME_CURVE})


@dataclass
class MarketSnapshot:
    quotes: dict[str, Quote] = field(default_factory=dict)
    fundamentals: dict[str, Fundamentals] = field(default_factory=dict)
    timed_out: list[str] = field(default_factory=list)


def fetch_market_data(
    gateway: CachedMarketGateway,
    assets: Iterable[AssetEntity],
    *,
    include_quotes: bool = True,
    include_fundamentals: bool = True,
    max_workers: int = 8,
    timeout_seconds: float = 20.0,
    bypass_cache: bool = False,
) -> MarketSnapshot:
    """Fetch quotes (and optionally fundamentals) for market-traded assets concurrently.

    `bypass_cache` asks the providers again (the worker refreshing the stored data).
    """
    tradable = [a for a in assets if a.market not in OFFLINE_MARKETS]
    result = MarketSnapshot()
    if not tradable:
        return result

    executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="market")
    futures: dict[Future, tuple[str, str]] = {}
    for asset in tradable:
        if include_quotes:
            quote_future = executor.submit(
                copy_context().run,
                lambda a=asset: gateway.get_quote(
                    a.ticker, asset_type=a.asset_type, bypass_cache=bypass_cache
                ),
            )
            futures[quote_future] = ("quote", asset.ticker)
        if include_fundamentals:
            future = executor.submit(
                copy_context().run,
                lambda a=asset: gateway.get_fundamentals(
                    a.ticker, asset_type=a.asset_type, bypass_cache=bypass_cache
                ),
            )
            futures[future] = ("fundamentals", asset.ticker)

    done, pending = wait(futures, timeout=timeout_seconds)
    executor.shutdown(wait=False, cancel_futures=True)

    for future in done:
        kind, ticker = futures[future]
        try:
            value = future.result()
        except Exception as exc:  # a provider bug must not break the valuation
            logger.warning("Market %s for %s failed: %s", kind, ticker, exc)
            continue
        if value is None:
            continue
        if kind == "quote":
            result.quotes[ticker] = value
        else:
            result.fundamentals[ticker] = value

    result.timed_out = sorted({futures[f][1] for f in pending})
    for future in pending:
        kind, ticker = futures[future]
        report_provider_error(
            provider="gateway",
            operation=kind,
            target=ticker,
            request_url=f"batch://{kind}/{ticker}",
            error_type="TimeoutError",
            error_detail=f"Batch market fetch timed out after {timeout_seconds:.1f}s",
        )
    if result.timed_out:
        logger.warning(
            "Market data timed out after %.1fs for: %s",
            timeout_seconds,
            ", ".join(result.timed_out),
        )
    return result


def fetch_histories(
    gateway: CachedMarketGateway,
    assets: Iterable[AssetEntity],
    *,
    range_period: str = "2y",
    max_workers: int = 8,
    timeout_seconds: float = 20.0,
    bypass_cache: bool = False,
) -> dict[str, list[PricePoint]]:
    """Daily price histories of market-traded assets, fetched concurrently with one deadline.

    Assets whose history fails or does not arrive in time are left out.
    """
    tradable = [a for a in assets if a.market not in OFFLINE_MARKETS]
    if not tradable:
        return {}
    executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="history")
    futures: dict[Future, str] = {
        executor.submit(
            copy_context().run,
            lambda a=asset: gateway.get_history(
                a.ticker,
                range_period=range_period,
                asset_type=a.asset_type,
                bypass_cache=bypass_cache,
            ),
        ): asset.ticker
        for asset in tradable
    }
    done, pending = wait(futures, timeout=timeout_seconds)
    executor.shutdown(wait=False, cancel_futures=True)
    histories: dict[str, list[PricePoint]] = {}
    for future in done:
        ticker = futures[future]
        try:
            points = future.result()
        except Exception as exc:  # a provider bug must not break the diagnosis
            logger.warning("History for %s failed: %s", ticker, exc)
            continue
        if points:
            histories[ticker] = sorted(points, key=lambda p: p.date)
    if pending:
        logger.warning(
            "Price history timed out after %.1fs for: %s",
            timeout_seconds,
            ", ".join(sorted(futures[f] for f in pending)),
        )
    return histories


def fetch_distributions(
    gateway: CachedMarketGateway,
    assets: Iterable[AssetEntity],
    *,
    max_workers: int = 8,
    timeout_seconds: float = 20.0,
    bypass_cache: bool = False,
) -> dict[str, AnnouncedDistributions]:
    """Declared dividends and stock events of B3 assets, fetched concurrently."""
    tradable = [a for a in assets if a.market not in OFFLINE_MARKETS]
    if not tradable:
        return {}
    executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="dividends")
    futures: dict[Future, str] = {
        executor.submit(
            copy_context().run,
            lambda a=asset: gateway.get_distributions(
                a.ticker, asset_type=a.asset_type, bypass_cache=bypass_cache
            ),
        ): asset.ticker
        for asset in tradable
    }
    done, _pending = wait(futures, timeout=timeout_seconds)
    executor.shutdown(wait=False, cancel_futures=True)
    found: dict[str, AnnouncedDistributions] = {}
    for future in done:
        try:
            found[futures[future]] = future.result()
        except Exception as exc:  # a provider bug must not break the agenda
            logger.warning("Distributions for %s failed: %s", futures[future], exc)
    return found
