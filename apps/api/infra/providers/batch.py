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

from domain.market.entities import Fundamentals, Quote
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
) -> MarketSnapshot:
    """Fetch quotes (and optionally fundamentals) for market-traded assets concurrently."""
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
                lambda a=asset: gateway.get_quote(a.ticker, asset_type=a.asset_type),
            )
            futures[quote_future] = ("quote", asset.ticker)
        if include_fundamentals:
            future = executor.submit(
                copy_context().run,
                lambda a=asset: gateway.get_fundamentals(a.ticker, asset_type=a.asset_type),
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
