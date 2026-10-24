"""Unit tests for Phase 3: Market Providers (Brapi, YFinance, BCB), Cache, Gateway & Analytics."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import httpx
import pandas as pd
import pytest
from fincontrol_core.analytics import (
     analyze_return_series,
    annualized_volatility,
    beta_alpha,
    build_base100_curve,
    cagr,
    calmar_ratio,
    conditional_var,
    correlation_matrix,
    cumulative_return,
    drawdown_series,
    historical_var,
    log_returns,
    max_drawdown,
    parametric_var,
    real_return_vs_inflation,
    sharpe_ratio,
    simple_returns,
    sortino_ratio,
    time_weighted_return,
)
from fincontrol_core.domain.entities import PortfolioSnapshotEntity
from fincontrol_core.domain.enums import AssetType, Market
from fincontrol_core.market.bcb import BcbSgsProvider
from fincontrol_core.market.brapi import BrapiProvider
from fincontrol_core.market.cache import InMemoryCache
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.market.models import QuoteFreshness
from fincontrol_core.market.yfinance_provider import YFinanceProvider, resolve_yahoo_symbol


# ---------------------------------------------------------------------------
# 1. BrapiProvider Tests (httpx.MockTransport)
# ---------------------------------------------------------------------------
def test_brapi_provider_quote_history_and_fundamentals() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "symbol": "WEGE3",
                        "longName": "WEG S.A.",
                        "currency": "BRL",
                        "regularMarketPrice": 52.40,
                        "regularMarketChangePercent": 1.85,
                        "regularMarketPreviousClose": 51.45,
                        "regularMarketVolume": 18_500_000,
                        "marketCap": 219_000_000_000,
                        "priceEarnings": 32.5,
                        "earningsPerShare": 1.61,
                        "historicalDataPrice": [
                            {"date": "2025-01-02", "close": 50.0, "open": 49.5, "volume": 1000},
                            {"date": "2025-01-03", "close": 52.4, "open": 50.2, "volume": 1200},
                        ],
                        "defaultKeyStatistics": {
                            "priceToBook": {"raw": 8.4},
                            "bookValue": {"raw": 6.23},
                        },
                        "financialData": {
                            "returnOnEquity": {"raw": 0.29},
                            "profitMargins": {"raw": 0.17},
                            "revenueGrowth": {"raw": 0.14},
                            "totalDebt": {"raw": 3_000_000_000},
                            "totalCash": {"raw": 5_000_000_000},
                            "ebitda": {"raw": 8_000_000_000},
                        },
                        "summaryDetail": {
                            "dividendYield": {"raw": 0.018},
                            "trailingAnnualDividendRate": {"raw": 0.94},
                        },
                        "summaryProfile": {"sector": "Industrials", "industry": "Electrical"},
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = BrapiProvider(token="test-token", client=client)

    quote = provider.get_quote("WEGE3")
    assert quote is not None
    assert quote.symbol == "WEGE3"
    assert quote.price == 52.40
    assert quote.provider == "brapi"
    assert quote.freshness == QuoteFreshness.LIVE

    history = provider.get_history("WEGE3", range_period="5d")
    assert len(history) == 2
    assert history[0].close == 50.0
    assert history[1].close == 52.4

    fund = provider.get_fundamentals("WEGE3")
    assert fund is not None
    assert fund.return_on_equity == 0.29
    assert fund.price_to_book == 8.4
    assert fund.net_debt_to_ebitda is not None and fund.net_debt_to_ebitda < 0


# ---------------------------------------------------------------------------
# 2. YFinanceProvider Tests (Injectable Fake Ticker)
# ---------------------------------------------------------------------------
class _FakeYFTicker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.info: dict[str, Any] = {
            "regularMarketPrice": 580.0 if symbol == "IVV" else 49.80,
            "previousClose": 575.0 if symbol == "IVV" else 49.00,
            "currency": "USD" if symbol == "IVV" else "BRL",
            "longName": f"Fake {symbol}",
            "trailingPE": 24.0,
            "priceToBook": 4.2,
            "trailingEps": 24.16,
            "bookValue": 138.0,
            "dividendYield": 1.4,
            "averageVolume": 1000.0,
            "returnOnEquity": 0.18,
            "profitMargins": 0.12,
        }

    def history(self, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        idx = pd.to_datetime(["2025-01-02", "2025-01-03"])
        return pd.DataFrame(
            {
                "Open": [100.0, 101.0],
                "High": [102.0, 105.0],
                "Low": [99.0, 100.5],
                "Close": [101.0, 104.0],
                "Volume": [5000.0, 6000.0],
            },
            index=idx,
        )


def test_yfinance_symbol_resolution_and_provider() -> None:
    assert resolve_yahoo_symbol("WEGE3", Market.B3) == "WEGE3.SA"
    assert resolve_yahoo_symbol("BTC", Market.CRYPTO) == "BTC-USD"
    assert resolve_yahoo_symbol("IBOV", Market.INDEX) == "^BVSP"
    assert resolve_yahoo_symbol("IFIX", Market.INDEX) == "IFIX.SA"
    assert resolve_yahoo_symbol("SP500", Market.INDEX) == "^GSPC"

    yf_prov = YFinanceProvider(ticker_factory=_FakeYFTicker)
    q = yf_prov.get_quote("IVV", market=Market.US)
    assert q is not None
    assert q.price == 580.0
    assert q.currency == "USD"

    hist = yf_prov.get_history("IVV", market=Market.US)
    assert len(hist) == 2
    assert hist[-1].close == 104.0

    fund = yf_prov.get_fundamentals("IVV", market=Market.US)
    assert fund is not None
    assert fund.price_to_earnings == 24.0
    # yfinance reports dividendYield in percent and averageVolume in shares (ADR 0006).
    assert fund.dividend_yield == pytest.approx(0.014)
    assert fund.avg_daily_volume == pytest.approx(580_000.0)


# ---------------------------------------------------------------------------
# 3. BcbSgsProvider Tests (CDI 12 & IPCA 433)
# ---------------------------------------------------------------------------
def test_bcb_sgs_provider_cdi_and_ipca() -> None:
    def bcb_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "bcdata.sgs.12" in url_str:
            return httpx.Response(
                200,
                json=[
                    {"data": "02/01/2025", "valor": "0.0402"},
                    {"data": "03/01/2025", "valor": "0.0402"},
                ],
            )
        if "bcdata.sgs.433" in url_str:
            return httpx.Response(
                200,
                json=[{"data": f"01/{m:02d}/2024", "valor": "0.38"} for m in range(1, 13)],
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(bcb_handler))
    bcb = BcbSgsProvider(client=client)

    cdi_pts = bcb.fetch_series("CDI", date(2025, 1, 1), date(2025, 1, 5))
    assert len(cdi_pts) == 2
    assert cdi_pts[-1].value == 0.0402

    annual_cdi = bcb.get_annualized_cdi_rate()
    assert 0.10 < annual_cdi < 0.12

    annual_ipca = bcb.get_annualized_ipca_rate()
    assert 0.04 < annual_ipca < 0.05


# ---------------------------------------------------------------------------
# 4. CachedMarketGateway & Automatic B3 Fallback Tests
# ---------------------------------------------------------------------------
def test_cached_market_gateway_caching_and_b3_fallback() -> None:
    def failing_brapi_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    brapi_down = BrapiProvider(
        client=httpx.Client(transport=httpx.MockTransport(failing_brapi_handler))
    )
    yf_ok = YFinanceProvider(ticker_factory=_FakeYFTicker)
    cache = InMemoryCache()
    gateway = CachedMarketGateway(brapi=brapi_down, yfinance=yf_ok, cache=cache)

    # First call for B3 asset falls back to YFinance (.SA) and marks freshness as FALLBACK
    q1 = gateway.get_quote("WEGE3", asset_type=AssetType.STOCK_BR)
    assert q1 is not None
    assert q1.price == 49.80
    assert q1.freshness == QuoteFreshness.FALLBACK

    # Second call hits cache and marks freshness as CACHED
    q2 = gateway.get_quote("WEGE3", asset_type=AssetType.STOCK_BR)
    assert q2 is not None
    assert q2.freshness == QuoteFreshness.CACHED


# ---------------------------------------------------------------------------
# 5. Quantitative & Statistical Risk Engine Tests (analytics.py)
# ---------------------------------------------------------------------------
def test_quantitative_analytics_and_benchmarks() -> None:
    prices = [100.0, 102.0, 101.0, 104.0, 106.0, 105.0, 108.0, 110.0, 109.0, 112.0]
    s_rets = simple_returns(prices)
    l_rets = log_returns(prices)
    assert len(s_rets) == 9
    assert len(l_rets) == 9
    assert math.isclose(cumulative_return(s_rets), 0.12, rel_tol=1e-6)

    # TWR isolating external net cash flow
    snapshots = [
        PortfolioSnapshotEntity(
            snapshot_date=date(2025, 1, 1),
            invested_value=10000.0,
            market_value=10000.0,
            unrealized_pnl=0.0,
            net_flow=0.0,
        ),
        PortfolioSnapshotEntity(
            snapshot_date=date(2025, 1, 2),
            invested_value=15000.0,
            market_value=15500.0,  # +5000 deposit, +500 market gain (5% return on 10000)
            unrealized_pnl=500.0,
            net_flow=5000.0,
        ),
    ]
    twr_rets = time_weighted_return(snapshots)
    assert len(twr_rets) == 1
    assert math.isclose(twr_rets[0], 0.05, rel_tol=1e-6)

    # Risk & return metrics
    vol = annualized_volatility(s_rets)
    assert vol > 0.0
    sr = sharpe_ratio(s_rets, annual_risk_free_rate=0.10)
    so = sortino_ratio(s_rets, annual_risk_free_rate=0.10)
    assert sr != 0.0
    assert so != 0.0

    dd = drawdown_series(s_rets)
    mdd = max_drawdown(s_rets)
    assert len(dd) == len(s_rets)
    assert mdd < 0.0
    assert calmar_ratio(s_rets) > 0.0
    assert cagr(0.12, 252) > 0.11
    assert real_return_vs_inflation(0.12, 0.045) > 0.07

    h_var = historical_var(s_rets, 0.95)
    p_var = parametric_var(s_rets, 0.95)
    c_var = conditional_var(s_rets, 0.95)
    assert h_var >= 0.0
    assert p_var >= 0.0
    assert c_var >= h_var

    ibov_rets = [r * 0.9 for r in s_rets]
    ifix_rets = [r * 0.5 for r in s_rets]
    sp500_rets = [r * 1.1 for r in s_rets]

    beta, alpha = beta_alpha(s_rets, ibov_rets, annual_risk_free_rate=0.10)
    assert beta is not None and beta > 1.0
    assert alpha is not None

    corr_mat = correlation_matrix(
        {"PORTFOLIO": s_rets, "IBOV": ibov_rets, "IFIX": ifix_rets, "SP500": sp500_rets}
    )
    assert corr_mat["PORTFOLIO"]["PORTFOLIO"] == 1.0
    assert corr_mat["PORTFOLIO"]["IBOV"] > 0.99

    curve = build_base100_curve([date(2025, 1, i) for i in range(1, 11)], s_rets)
    assert curve[0]["value"] == 100.0
    assert curve[-1]["value"] == 112.0

    summary = analyze_return_series(
        s_rets,
        benchmark_returns_map={"IBOV": ibov_rets, "IFIX": ifix_rets, "SP500": sp500_rets},
        annual_cdi_rate=0.1075,
        annual_ipca_rate=0.045,
    )
    bench_names = {b.benchmark for b in summary.benchmarks}
    assert {"IBOV", "IFIX", "SP500", "CDI", "IPCA"}.issubset(bench_names)
