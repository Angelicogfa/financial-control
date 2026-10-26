"""Providers offline: failures are remembered briefly so screens answer at once (item 14.3)."""

from __future__ import annotations

from typing import Any

import httpx
from fincontrol_core.domain.enums import AssetType
from fincontrol_core.market.bcb import BcbSgsProvider
from fincontrol_core.market.brapi import BrapiProvider
from fincontrol_core.market.cache import InMemoryCache
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.market.yfinance_provider import YFinanceProvider


class _Down:
    calls = 0

    def __init__(self, symbol: str) -> None:
        _Down.calls += 1
        raise RuntimeError("Yahoo is down")


def _gateway(miss_ttl: int = 300) -> tuple[CachedMarketGateway, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def brapi(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(503)

    _Down.calls = 0
    gateway = CachedMarketGateway(
        brapi=BrapiProvider(client=httpx.Client(transport=httpx.MockTransport(brapi))),
        yfinance=YFinanceProvider(ticker_factory=_Down),
        bcb=BcbSgsProvider(
            client=httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(503)))
        ),
        cache=InMemoryCache(),
        miss_ttl_seconds=miss_ttl,
    )
    return gateway, seen


def test_failures_are_remembered_until_the_miss_ttl() -> None:
    gateway, seen = _gateway()
    calls: list[Any] = [
        lambda: gateway.get_quote("WEGE3"),
        lambda: gateway.get_fundamentals("WEGE3"),
        lambda: gateway.get_history("WEGE3"),
        lambda: gateway.get_annual_statements("WEGE3"),
    ]
    assert [call() for call in calls] == [None, None, [], []]
    first_round = (len(seen), _Down.calls)
    assert first_round[0] > 0 and first_round[1] > 0
    assert [call() for call in calls] == [None, None, [], []]
    assert (len(seen), _Down.calls) == first_round  # nothing asked again


def test_bypass_cache_retries_and_zero_ttl_disables_the_memory() -> None:
    gateway, seen = _gateway()
    gateway.get_quote("AAPL", asset_type=AssetType.STOCK_INTL)
    gateway.get_quote("AAPL", asset_type=AssetType.STOCK_INTL, bypass_cache=True)
    assert _Down.calls == 2

    no_memory, seen = _gateway(miss_ttl=0)
    no_memory.get_quote("WEGE3")
    no_memory.get_quote("WEGE3")
    assert len(seen) == 2


def test_rates_fall_back_to_the_configured_defaults() -> None:
    gateway, _ = _gateway()
    cdi, ipca = gateway.get_macro_rates()
    assert cdi > 0 and ipca > 0
    assert gateway.get_usd_brl_rate() == gateway.default_usd_brl
