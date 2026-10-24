"""Unit tests for CachedMarketGateway routing/caching and cache backends (in-memory only)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fincontrol_core.domain.entities import MarketSeriesPoint
from fincontrol_core.domain.enums import AssetType, Market
from fincontrol_core.market import cache as cache_module
from fincontrol_core.market.cache import InMemoryCache, RedisCache, build_cache_backend
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.market.models import Fundamentals, PricePoint, Quote, QuoteFreshness


class _FakeProvider:
    """Records calls and returns preconfigured quote/history/fundamentals."""

    def __init__(
        self,
        quote: Quote | None = None,
        history: list[PricePoint] | None = None,
        fundamentals: Fundamentals | None = None,
    ) -> None:
        self.quote = quote
        self.history = history or []
        self.fundamentals = fundamentals
        self.calls: list[tuple[str, str, Any]] = []

    def get_quote(self, symbol: str, market: Market | None = None) -> Quote | None:
        self.calls.append(("quote", symbol, market))
        return self.quote

    def get_history(
        self, symbol: str, range_period: str = "1y", market: Market | None = None
    ) -> list[PricePoint]:
        self.calls.append(("history", symbol, market))
        return self.history

    def get_fundamentals(self, symbol: str, market: Market | None = None) -> Fundamentals | None:
        self.calls.append(("fundamentals", symbol, market))
        return self.fundamentals


class _FakeBcb:
    def __init__(self) -> None:
        self.rate_calls = 0

    def get_annualized_cdi_rate(self) -> float:
        self.rate_calls += 1
        return 0.149

    def get_annualized_ipca_rate(self) -> float:
        return 0.046

    def fetch_series(
        self, symbol: str, start_date: date | None = None, end_date: date | None = None
    ) -> list[MarketSeriesPoint]:
        return [MarketSeriesPoint(symbol, start_date or date(2025, 1, 2), 0.05)]


def _gateway(
    brapi: _FakeProvider | None = None,
    yfinance: _FakeProvider | None = None,
    bcb: _FakeBcb | None = None,
) -> CachedMarketGateway:
    return CachedMarketGateway(
        brapi=brapi or _FakeProvider(),  # type: ignore[arg-type]
        yfinance=yfinance or _FakeProvider(),  # type: ignore[arg-type]
        bcb=bcb or _FakeBcb(),  # type: ignore[arg-type]
        cache=InMemoryCache(),
        default_usd_brl=5.25,
    )


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("^BVSP", Market.INDEX),
        ("USDBRL=X", Market.INDEX),
        ("PETR4", Market.B3),
        ("AAPL", Market.US),
    ],
)
def test_resolve_market_heuristics(symbol: str, expected: Market) -> None:
    assert _gateway()._resolve_market(symbol) == expected


def test_resolve_market_prefers_explicit_market_and_asset_type() -> None:
    gw = _gateway()
    assert gw._resolve_market("PETR4", market=Market.US) == Market.US
    assert gw._resolve_market("BTC", asset_type=AssetType.CRYPTO) == Market.CRYPTO


def test_quote_is_cached_and_marked_as_cached() -> None:
    brapi = _FakeProvider(quote=Quote(symbol="PETR4", price=38.0))
    gw = _gateway(brapi=brapi)

    first = gw.get_quote("petr4")
    second = gw.get_quote("PETR4")

    assert first is not None and first.freshness == QuoteFreshness.LIVE
    assert second is not None and second.freshness == QuoteFreshness.CACHED
    assert len(brapi.calls) == 1


def test_b3_quote_falls_back_to_yfinance() -> None:
    yfinance = _FakeProvider(quote=Quote(symbol="PETR4", price=37.5))
    gw = _gateway(yfinance=yfinance)

    quote = gw.get_quote("PETR4", bypass_cache=True)

    assert quote is not None and quote.freshness == QuoteFreshness.FALLBACK
    assert yfinance.calls == [("quote", "PETR4", Market.B3)]


def test_manual_and_curve_assets_have_no_market_data() -> None:
    gw = _gateway()
    assert gw.get_quote("CAIXA", asset_type=AssetType.CASH) is None
    assert gw.get_history("CDB", asset_type=AssetType.FIXED_INCOME) == []
    assert gw.get_fundamentals("BTC", asset_type=AssetType.CRYPTO) is None


def test_history_uses_fallback_and_cache() -> None:
    points = [PricePoint(date=date(2025, 1, 2), close=10.0)]
    yfinance = _FakeProvider(history=points)
    gw = _gateway(yfinance=yfinance)

    assert gw.get_history("WEGE3") == points
    assert gw.get_history("WEGE3") == points
    assert len(yfinance.calls) == 1


def test_us_history_and_fundamentals_route_to_yfinance() -> None:
    fundamentals = Fundamentals(symbol="AAPL", return_on_equity=1.6)
    yfinance = _FakeProvider(
        history=[PricePoint(date=date(2025, 1, 2), close=200.0)], fundamentals=fundamentals
    )
    gw = _gateway(yfinance=yfinance)

    assert gw.get_history("AAPL")[0].close == 200.0
    assert gw.get_fundamentals("AAPL") == fundamentals
    assert gw.get_fundamentals("AAPL") == fundamentals
    assert [c[0] for c in yfinance.calls] == ["history", "fundamentals"]


def test_b3_fundamentals_fall_back_to_yfinance() -> None:
    fundamentals = Fundamentals(symbol="WEGE3", price_to_earnings=30.0)
    gw = _gateway(yfinance=_FakeProvider(fundamentals=fundamentals))
    assert gw.get_fundamentals("WEGE3") == fundamentals


def test_usd_brl_rate_uses_quote_or_default() -> None:
    assert _gateway().get_usd_brl_rate() == 5.25
    live = _gateway(yfinance=_FakeProvider(quote=Quote(symbol="USDBRL=X", price=5.6)))
    assert live.get_usd_brl_rate() == 5.6


def test_macro_rates_are_cached() -> None:
    bcb = _FakeBcb()
    gw = _gateway(bcb=bcb)

    assert gw.get_macro_rates() == (0.149, 0.046)
    assert gw.get_macro_rates() == (0.149, 0.046)
    assert bcb.rate_calls == 1


def test_fetch_bcb_series_delegates_to_provider() -> None:
    points = _gateway().fetch_bcb_series("CDI", start_date=date(2025, 3, 3))
    assert points[0].reference_date == date(2025, 3, 3)


# ---------------------------------------------------------------------------
# Cache backends
# ---------------------------------------------------------------------------
def test_in_memory_cache_expires_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 1000.0}
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: clock["now"])
    cache = InMemoryCache()

    cache.set_json("k", {"v": 1}, ttl_seconds=10)
    assert cache.get_json("k") == {"v": 1}

    clock["now"] += 11
    assert cache.get_json("k") is None


def test_in_memory_cache_ignores_non_positive_ttl_and_clears() -> None:
    cache = InMemoryCache()
    cache.set_json("skip", [1], ttl_seconds=0)
    cache.set_json("keep", [2], ttl_seconds=60)

    assert cache.get_json("skip") is None
    cache.clear()
    assert cache.get_json("keep") is None


class _FailingRedis:
    def get(self, _key: str) -> str:
        raise ConnectionError("redis down")

    def setex(self, _key: str, _ttl: int, _payload: str) -> None:
        raise ConnectionError("redis down")


class _DictRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def setex(self, key: str, _ttl: int, payload: str) -> None:
        self.store[key] = payload


def test_redis_cache_round_trip() -> None:
    cache = RedisCache("redis://localhost:6379/0")
    cache._client = _DictRedis()  # type: ignore[assignment]

    cache.set_json("k", {"v": 2}, ttl_seconds=30)
    cache.set_json("skip", {"v": 3}, ttl_seconds=0)

    assert cache.get_json("k") == {"v": 2}
    assert cache.get_json("skip") is None


def test_redis_cache_falls_back_to_memory_when_unavailable() -> None:
    cache = RedisCache("redis://localhost:6379/0")
    cache._client = _FailingRedis()  # type: ignore[assignment]

    cache.set_json("k", {"v": 1}, ttl_seconds=30)

    assert cache.get_json("k") == {"v": 1}


def test_build_cache_backend_selects_implementation() -> None:
    assert isinstance(build_cache_backend(None), InMemoryCache)
    assert isinstance(build_cache_backend("   "), InMemoryCache)
    assert isinstance(build_cache_backend("redis://localhost:6379/0"), RedisCache)
