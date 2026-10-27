"""Provider guards against plan limits and legacy config (worker error notifications)."""

from __future__ import annotations

import threading
import time
from datetime import date
from typing import Any

import httpx
import pytest

from core.settings import Settings
from infra.cache.redis_cache import InMemoryCache
from infra.providers.bcb import BcbSgsProvider
from infra.providers.brapi import BrapiProvider, range_within
from infra.providers.error_tracker import capture_worker_request_errors
from infra.providers.factory import build_market_gateway
from infra.providers.gateway import CachedMarketGateway
from infra.providers.yfinance_provider import YFinanceProvider


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.bcb.gov.br/dados/serie",
        "https://api.bcb.gov.br/dados/serie/",
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs",
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs/",
    ],
)
def test_bcb_accepts_base_url_with_or_without_sgs_suffix(base_url: str) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json=[{"data": "02/01/2025", "valor": "0.041"}])

    provider = BcbSgsProvider(
        base_url=base_url, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    points = provider.fetch_series("CDI", date(2025, 1, 1), date(2025, 1, 3))

    assert paths == ["/dados/serie/bcdata.sgs.12/dados"]
    assert len(points) == 1


@pytest.mark.parametrize(
    ("range_period", "max_range", "allowed"),
    [
        ("5d", "3mo", True),
        ("3mo", "3mo", True),
        ("1y", "3mo", False),
        ("5y", "3mo", False),
        ("ytd", "1y", True),
        ("5y", None, True),
        ("5y", "", True),
        ("custom", "3mo", True),
    ],
)
def test_range_within_plan(range_period: str, max_range: str | None, allowed: bool) -> None:
    assert range_within(range_period, max_range) is allowed


def test_brapi_skips_ranges_beyond_the_plan_without_requesting() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"results": []})

    provider = BrapiProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)), max_history_range="3mo"
    )
    with capture_worker_request_errors("backfill_snapshots") as recorder:
        assert provider.get_history("XPML11", range_period="5y") == []

    assert calls == []
    assert recorder.drain() == []


class _YahooHistory:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.info: dict[str, Any] = {}

    def history(self, period: str = "1y", interval: str = "1d") -> Any:
        import pandas as pd

        return pd.DataFrame(
            {"Close": [10.0, 11.0]}, index=pd.to_datetime(["2021-01-04", "2021-01-05"])
        )


def test_gateway_uses_yahoo_for_history_beyond_the_brapi_plan() -> None:
    brapi_calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        brapi_calls.append(request)
        return httpx.Response(400, json={"error": True, "code": "INVALID_RANGE"})

    gateway = CachedMarketGateway(
        brapi=BrapiProvider(
            client=httpx.Client(transport=httpx.MockTransport(handler)), max_history_range="3mo"
        ),
        yfinance=YFinanceProvider(ticker_factory=_YahooHistory),
        bcb=BcbSgsProvider(),
        cache=InMemoryCache(),
    )

    history = gateway.get_history("ITUB4", range_period="5y", market=None)

    assert brapi_calls == []
    assert [p.close for p in history] == [10.0, 11.0]


def test_brapi_never_exceeds_the_concurrency_limit() -> None:
    lock = threading.Lock()
    active = 0
    peak = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return httpx.Response(200, json={"results": [{"regularMarketPrice": 10.0}]})

    provider = BrapiProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)), max_concurrency=1
    )
    threads = [threading.Thread(target=provider.get_quote, args=(f"T{i}",)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert peak == 1


def test_factory_applies_the_brapi_plan_limits() -> None:
    settings = Settings(_env_file=None, brapi_max_history_range="6mo", brapi_max_concurrency=2)

    brapi = build_market_gateway(settings).brapi

    assert brapi.max_history_range == "6mo"
    assert brapi._slots._value == 2  # type: ignore[attr-defined]


def test_settings_default_to_the_free_brapi_plan() -> None:
    settings = Settings(_env_file=None)

    assert settings.brapi_max_history_range == "3mo"
    assert settings.brapi_max_concurrency == 1
