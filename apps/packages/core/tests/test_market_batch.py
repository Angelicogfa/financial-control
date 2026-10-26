"""Unit tests for concurrent market data retrieval (findings D-05, I-07)."""

from __future__ import annotations

import threading
import time
from decimal import Decimal

from fincontrol_core.domain.entities import AssetEntity
from fincontrol_core.domain.enums import AssetType
from fincontrol_core.market.batch import fetch_market_data
from fincontrol_core.market.models import Fundamentals, Quote


class _SlowGateway:
    def __init__(self, delay: float, slow_ticker: str | None = None) -> None:
        self.delay = delay
        self.slow_ticker = slow_ticker
        self.active = 0
        self.peak = 0
        self._lock = threading.Lock()

    def _enter(self, ticker: str) -> None:
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(5.0 if ticker == self.slow_ticker else self.delay)
        with self._lock:
            self.active -= 1

    def get_quote(self, ticker: str, asset_type: AssetType) -> Quote | None:
        self._enter(ticker)
        if ticker == "BROKEN3":
            raise RuntimeError("provider bug")
        return Quote(ticker, 10.0)

    def get_fundamentals(self, ticker: str, asset_type: AssetType) -> Fundamentals | None:
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
