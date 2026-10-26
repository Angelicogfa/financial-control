"""Unit tests for yearly statement history, derived metrics and provider adapters (11.1, 11.2)."""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pandas as pd
import pytest

from domain.assets.services.history import (
    FundamentalPeriod,
    FundamentalSnapshot,
    historical_metrics,
    snapshot_from_dict,
    snapshot_to_dict,
)
from domain.shared.enums import AssetType
from infra.cache.redis_cache import InMemoryCache
from infra.providers.bcb import BcbSgsProvider
from infra.providers.brapi import BrapiProvider, parse_brapi_statements
from infra.providers.gateway import CachedMarketGateway
from infra.providers.yfinance_provider import YFinanceProvider, parse_yfinance_statements


def _year(year: int, **metrics: float | None) -> FundamentalSnapshot:
    return FundamentalSnapshot("WEGE3", date(year, 12, 31), FundamentalPeriod.ANNUAL, metrics)


def test_historical_metrics_over_window() -> None:
    snapshots = [
        _year(2019, revenue=50.0, net_income=1.0, equity=10.0, dividends_paid=-0.5),
        _year(2020, revenue=100.0, net_income=10.0, equity=100.0, dividends_paid=-5.0),
        _year(2021, revenue=110.0, net_income=12.0, equity=100.0, dividends_paid=-6.0),
        _year(2022, revenue=121.0, net_income=-2.0, equity=100.0, dividends_paid=0.0),
        _year(2023, revenue=133.1, net_income=14.0, equity=100.0, dividends_paid=-7.0),
        _year(2024, revenue=146.41, net_income=16.0, equity=100.0, dividends_paid=-8.0),
    ]
    metrics = historical_metrics(snapshots, window_years=5)

    assert (metrics.years, metrics.first_year, metrics.last_year) == (5, 2020, 2024)
    assert metrics.revenue_cagr == pytest.approx(0.10)
    assert metrics.earnings_cagr == pytest.approx((16 / 10) ** 0.25 - 1)
    assert metrics.roe_average == pytest.approx((0.10 + 0.12 - 0.02 + 0.14 + 0.16) / 5)
    assert metrics.profitable_years == 4
    assert not metrics.always_profitable
    assert metrics.dividend_years == 4
    assert metrics.dividend_regularity == pytest.approx(0.8)
    # Payout skips the loss year (undefined) and averages the others.
    assert metrics.payout_average == pytest.approx(0.5)


def test_historical_metrics_ignores_ttm_and_handles_empty() -> None:
    ttm = FundamentalSnapshot("X", date(2024, 6, 30), FundamentalPeriod.TTM, {"revenue": 1.0})
    empty = historical_metrics([ttm])
    assert empty.years == 0
    assert empty.dividend_regularity is None
    assert not empty.always_profitable


def test_cagr_undefined_for_non_positive_endpoints() -> None:
    metrics = historical_metrics(
        [_year(2022, revenue=0.0, net_income=-1.0), _year(2023, revenue=10.0, net_income=2.0)]
    )
    assert metrics.revenue_cagr is None
    assert metrics.earnings_cagr is None


def test_snapshot_dict_round_trip() -> None:
    snapshot = _year(2023, revenue=1.0, net_income=None)
    assert snapshot_from_dict(snapshot_to_dict(snapshot)) == FundamentalSnapshot(
        "WEGE3", date(2023, 12, 31), FundamentalPeriod.ANNUAL, {"revenue": 1.0, "net_income": None}
    )


BRAPI_ITEM: dict[str, Any] = {
    "incomeStatementHistory": [
        {"endDate": "2023-12-31", "totalRevenue": 100.0, "netIncome": 10.0, "ebit": 15.0},
        {"endDate": "2022-12-31", "totalRevenue": 90.0, "netIncome": 9.0},
    ],
    "balanceSheetHistory": {
        "balanceSheetStatements": [
            {
                "endDate": {"raw": 1703980800, "fmt": "2023-12-31"},
                "totalStockholderEquity": {"raw": 80.0},
                "cash": 5.0,
                "longTermDebt": 20.0,
            }
        ]
    },
    "cashflowHistory": [{"endDate": "2023-12-31", "dividendsPaid": -4.0}, {"endDate": None}],
}


def test_parse_brapi_statements_merges_modules_by_year() -> None:
    snapshots = parse_brapi_statements("WEGE3", BRAPI_ITEM)
    assert [s.reference_date for s in snapshots] == [date(2022, 12, 31), date(2023, 12, 31)]
    latest = snapshots[-1]
    assert latest.metrics == {
        "revenue": 100.0,
        "net_income": 10.0,
        "ebitda": 15.0,
        "equity": 80.0,
        "cash": 5.0,
        "total_debt": 20.0,
        "dividends_paid": -4.0,
    }
    assert latest.source == BrapiProvider.PROVIDER_NAME


def test_brapi_annual_statements_requests_modules_and_tolerates_errors() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"results": [BRAPI_ITEM]})

    provider = BrapiProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert len(provider.get_annual_statements("wege3.sa")) == 2
    assert seen[0].url.path.endswith("/quote/WEGE3")
    assert "balanceSheetHistory" in seen[0].url.params["modules"]

    failing = BrapiProvider(
        client=httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(500)))
    )
    assert failing.get_annual_statements("WEGE3") == []


class _StatementTicker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        cols = pd.to_datetime(["2023-12-31", "2022-12-31"])
        self.income_stmt = pd.DataFrame(
            {cols[0]: [200.0, 20.0], cols[1]: [180.0, float("nan")]},
            index=["Total Revenue", "Net Income"],
        )
        self.balance_sheet = pd.DataFrame(
            {cols[0]: [150.0], cols[1]: [140.0]}, index=["Stockholders Equity"]
        )
        self.cashflow = pd.DataFrame()


def test_parse_yfinance_statements_reads_dataframes() -> None:
    snapshots = parse_yfinance_statements("aapl", _StatementTicker("AAPL"))
    assert [s.reference_date for s in snapshots] == [date(2022, 12, 31), date(2023, 12, 31)]
    assert snapshots[0].metrics == {"revenue": 180.0, "equity": 140.0}
    assert snapshots[1].metrics == {"revenue": 200.0, "net_income": 20.0, "equity": 150.0}
    assert snapshots[1].ticker == "AAPL"


def test_yfinance_annual_statements_returns_empty_on_failure() -> None:
    def broken(_symbol: str) -> Any:
        raise RuntimeError("offline")

    assert YFinanceProvider(ticker_factory=broken).get_annual_statements("AAPL") == []


def _gateway(brapi_payload: dict[str, Any] | None) -> CachedMarketGateway:
    def handler(_request: httpx.Request) -> httpx.Response:
        if brapi_payload is None:
            return httpx.Response(404)
        return httpx.Response(200, json=brapi_payload)

    return CachedMarketGateway(
        brapi=BrapiProvider(client=httpx.Client(transport=httpx.MockTransport(handler))),
        yfinance=YFinanceProvider(ticker_factory=_StatementTicker),
        bcb=BcbSgsProvider(
            client=httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(500)))
        ),
        cache=InMemoryCache(),
    )


def test_gateway_prefers_brapi_for_b3_and_caches() -> None:
    gateway = _gateway({"results": [BRAPI_ITEM]})
    first = gateway.get_annual_statements("WEGE3")
    assert first[-1].source == BrapiProvider.PROVIDER_NAME
    gateway.brapi = BrapiProvider(
        client=httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(500)))
    )
    assert gateway.get_annual_statements("WEGE3") == first


def test_gateway_falls_back_to_yfinance_and_skips_non_equities() -> None:
    gateway = _gateway(None)
    snapshots = gateway.get_annual_statements("WEGE3")
    assert snapshots and snapshots[0].source == YFinanceProvider.PROVIDER_NAME
    assert gateway.get_annual_statements("BTC", asset_type=AssetType.CRYPTO) == []
    assert gateway.get_annual_statements("AAPL")[0].source == YFinanceProvider.PROVIDER_NAME
