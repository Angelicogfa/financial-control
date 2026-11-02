"""Unit tests for concurrent market data retrieval (findings D-05, I-07)."""

from __future__ import annotations

import threading
import time
from decimal import Decimal

from domain.market.entities import Fundamentals, Quote
from domain.market.services.batch import fetch_market_data
from domain.shared.entities import AssetEntity
from domain.shared.enums import AssetType
from infra.cache.redis_cache import InMemoryCache
from infra.providers.error_tracker import capture_worker_request_errors
from infra.providers.gateway import CachedMarketGateway


class _SlowGateway:
    def __init__(self, delay: float, slow_ticker: str | None = None) -> None:
        self.delay = delay
        self.slow_ticker = slow_ticker
        self.active = 0
        self.peak = 0
        self._lock = threading.Lock()
        self.timeouts: list[tuple[str, str, float]] = []

    def report_fetch_timeout(self, kind: str, ticker: str, timeout_seconds: float) -> None:
        self.timeouts.append((kind, ticker, timeout_seconds))

    def _enter(self, ticker: str) -> None:
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(5.0 if ticker == self.slow_ticker else self.delay)
        with self._lock:
            self.active -= 1

    def get_quote(
        self, ticker: str, asset_type: AssetType, bypass_cache: bool = False
    ) -> Quote | None:
        self._enter(ticker)
        if ticker == "BROKEN3":
            raise RuntimeError("provider bug")
        return Quote(ticker, 10.0)

    def get_fundamentals(
        self, ticker: str, asset_type: AssetType, bypass_cache: bool = False
    ) -> Fundamentals | None:
        self._enter(ticker)
        return None


def _stock(ticker: str) -> AssetEntity:
    return AssetEntity(ticker=ticker, name=ticker, asset_type=AssetType.STOCK_BR)


def test_fetches_concurrently_and_skips_offline_assets() -> None:
    gateway = _SlowGateway(delay=0.2)
    assets = [_stock(f"TST{i}3") for i in range(8)] + [
        AssetEntity(
            ticker="CAIXA", name="Caixa", asset_type=AssetType.CASH, manual_price=Decimal(1)
        )
    ]

    started = time.perf_counter()
    snapshot = fetch_market_data(gateway, assets, max_workers=8, timeout_seconds=5)  # type: ignore[arg-type]
    elapsed = time.perf_counter() - started

    assert len(snapshot.quotes) == 8
    assert "CAIXA" not in snapshot.quotes
    assert snapshot.fundamentals == {}
    assert gateway.peak > 1
    assert elapsed < 1.5


def test_timeout_and_provider_errors_do_not_block_valuation() -> None:
    gateway = _SlowGateway(delay=0.01, slow_ticker="SLOW3")
    assets = [_stock("FAST3"), _stock("SLOW3"), _stock("BROKEN3")]

    started = time.perf_counter()
    snapshot = fetch_market_data(
        gateway,  # type: ignore[arg-type]
        assets,
        include_fundamentals=False,
        timeout_seconds=0.5,
    )

    assert time.perf_counter() - started < 2.0
    assert set(snapshot.quotes) == {"FAST3"}
    assert snapshot.timed_out == ["SLOW3"]
    assert gateway.timeouts == [("quote", "SLOW3", 0.5)]


def test_gateway_records_a_batch_timeout_as_a_worker_request_error() -> None:
    gateway = CachedMarketGateway(cache=InMemoryCache())

    with capture_worker_request_errors("warm_portfolio_quotes") as recorder:
        gateway.report_fetch_timeout("quote", "SLOW3", 0.5)

    [error] = recorder.drain()
    assert (error.provider, error.operation, error.target) == ("gateway", "quote", "SLOW3")
    assert error.request_url == "batch://quote/SLOW3"
    assert error.error_type == "TimeoutError"
    assert "0.5s" in error.error_detail
