"""Every screen keeps working with the market providers offline (item 14.3).

Quotes fall back to the average price (flagged FALLBACK), alerts say so, and no endpoint
answers 500 — the user sees warnings, never invented numbers.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fincontrol_api.composition import get_market_gateway
from fincontrol_core.market.bcb import BcbSgsProvider
from fincontrol_core.market.brapi import BrapiProvider
from fincontrol_core.market.cache import InMemoryCache
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.market.yfinance_provider import YFinanceProvider

FIXTURES = Path(__file__).parent / "fixtures"


def _down(_symbol: str) -> object:
    raise RuntimeError("Yahoo is down")


@pytest.fixture
def offline(api: SimpleNamespace) -> SimpleNamespace:
    def refuse(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network unreachable")

    gateway = CachedMarketGateway(
        brapi=BrapiProvider(client=httpx.Client(transport=httpx.MockTransport(refuse))),
        yfinance=YFinanceProvider(ticker_factory=_down),
        bcb=BcbSgsProvider(client=httpx.Client(transport=httpx.MockTransport(refuse))),
        cache=InMemoryCache(),
    )
    api.app.dependency_overrides[get_market_gateway] = lambda: gateway
    client = api.client
    response = client.post(
        "/api/v1/imports/b3/commit",
        files={"file": ("b3_negociacao.csv", (FIXTURES / "b3_negociacao.csv").read_bytes())},
        data={"create_tickers": "ITSA4,HGLG11,WEGE3"},
    )
    assert response.status_code == 200, response.text
    return api


def test_screens_answer_with_providers_offline(offline: SimpleNamespace) -> None:
    client = offline.client
    report = client.get("/api/v1/portfolio/consolidated").json()
    positions = {p["ticker"]: p for p in report["positions"]}
    assert positions["WEGE3"]["price_freshness"] == "FALLBACK"
    assert positions["WEGE3"]["current_unit_price"] == pytest.approx(
        positions["WEGE3"]["average_price"]
    )

    keys = {a["key"] for a in client.get("/api/v1/alerts").json()["alerts"]}
    assert "fallback:WEGE3" in keys
    assert any(k.startswith("series:CDI") for k in keys)

    asset_id = positions["WEGE3"]["asset_id"]
    for path in (
        "/api/v1/portfolio/analytics",
        "/api/v1/portfolio/snapshots",
        f"/api/v1/assets/{asset_id}/analysis",
        "/api/v1/research/watchlist",
        "/api/v1/research/screener?min_dy=0.05",
        "/api/v1/market/series-status",
        "/api/v1/market/job-runs",
        "/api/v1/policy",
        "/api/v1/transactions",
    ):
        assert client.get(path).status_code == 200, path

    analysis = client.get(f"/api/v1/assets/{asset_id}/analysis").json()
    assert analysis["fundamentals"] is None
    assert analysis["valuation"]["verdict"] == "UNDEFINED"

    plan = client.post("/api/v1/contributions", json={"amount_brl": 1000.0})
    assert plan.status_code == 201


def test_follow_needs_a_type_when_the_catalog_is_empty(offline: SimpleNamespace) -> None:
    client = offline.client
    unknown = client.post("/api/v1/research/watchlist", json={"ticker": "BBAS3"})
    assert unknown.status_code == 400
    typed = client.post(
        "/api/v1/research/watchlist", json={"ticker": "BBAS3", "asset_type": "STOCK_BR"}
    )
    assert typed.status_code == 201
    assert typed.json()["valuation_verdict"] == "UNDEFINED"
