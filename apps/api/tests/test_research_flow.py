"""Acceptance test of the research flow with recorded brapi payloads (phase 11).

Catalog sync -> screener -> watchlist -> statements -> checklist -> analysis -> removal.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fincontrol_api.composition import get_market_gateway
from fincontrol_core.market.bcb import BcbSgsProvider
from fincontrol_core.market.brapi import BrapiProvider
from fincontrol_core.market.cache import InMemoryCache
from fincontrol_core.market.gateway import CachedMarketGateway
from fincontrol_core.market.yfinance_provider import YFinanceProvider

RECORDED = json.loads(
    (Path(__file__).parent / "fixtures" / "brapi_research.json").read_text(encoding="utf-8")
)


class _NoYahoo:
    """Yahoo stays offline: every figure comes from the recorded brapi payloads."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.info: dict[str, Any] = {}

    def history(self, period: str = "1y", interval: str = "1d") -> Any:
        import pandas as pd

        return pd.DataFrame()


def _recorded_brapi(request: httpx.Request) -> httpx.Response:
    path = request.url.path.rstrip("/")
    if path.endswith("/quote/list"):
        return httpx.Response(200, json=RECORDED["list"])
    ticker = path.rsplit("/", 1)[-1]
    quote = RECORDED["quotes"].get(ticker)
    if quote is None:
        return httpx.Response(404, json={"error": True})
    return httpx.Response(200, json={"results": [quote]})


@pytest.fixture
def research(api: SimpleNamespace) -> Iterator[SimpleNamespace]:
    gateway = CachedMarketGateway(
        brapi=BrapiProvider(client=httpx.Client(transport=httpx.MockTransport(_recorded_brapi))),
        yfinance=YFinanceProvider(ticker_factory=_NoYahoo),
        bcb=BcbSgsProvider(
            client=httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(500)))
        ),
        cache=InMemoryCache(),
    )
    api.app.dependency_overrides[get_market_gateway] = lambda: gateway
    with api.uow_factory() as uow:  # what sync_instrument_catalog_job stores
        uow.catalog.upsert(gateway.list_instruments())
        uow.commit()
    yield SimpleNamespace(**vars(api), gateway=gateway)


def _tickers(body: dict[str, Any]) -> list[str]:
    return [r["ticker"] for r in body["results"]]


def test_research_flow_from_screener_to_analysis(research: SimpleNamespace) -> None:
    client = research.client

    # Catalog-only filters, in volume order; funds split into FII and ETF.
    banks = client.get("/api/v1/research/screener", params={"sector": "finance"}).json()
    assert banks["catalog_size"] == 7
    assert _tickers(banks) == ["ITUB4", "BBAS3", "TINY3"]
    funds = client.get("/api/v1/research/screener", params={"asset_type": ["FII", "ETF_BR"]}).json()
    assert {r["ticker"]: r["asset_type"] for r in funds["results"]} == {
        "BOVA11": "ETF_BR",
        "HGLG11": "FII",
    }

    # Fundamental filters load indicators for the candidates only.
    screened = client.get(
        "/api/v1/research/screener",
        params={"asset_type": "STOCK_BR", "min_dy": 0.05, "max_pe": 10, "min_volume_brl": 1e6},
    ).json()
    assert _tickers(screened) == ["ITUB4", "BBAS3"]
    assert screened["candidates"] == 3 and screened["scanned"] == 3
    itub = screened["results"][0]
    assert itub["dividend_yield"] == pytest.approx(0.07)
    assert itub["arca_class"] == "ACOES"
    assert itub["valuation_verdict"] in {"DISCOUNTED", "FAIR", "EXPENSIVE"}
    assert itub["asset_id"] is None

    # Follow ITUB4 in the watchlist.
    added = client.post("/api/v1/research/watchlist", json={"ticker": "itub4"})
    assert added.status_code == 201, added.text
    item = added.json()
    assert (item["ticker"], item["asset_type"]) == ("ITUB4", "STOCK_BR")
    assert item["lifecycle_status"] in {"WATCHLIST", "ELIGIBLE"}
    asset_id = item["asset_id"]
    assert client.post("/api/v1/research/watchlist", json={"ticker": "ITUB4"}).status_code == 409

    # Weekly statements job, then the bank profile for the checklist.
    with research.uow_factory() as uow:
        uow.fundamentals.upsert(research.gateway.get_annual_statements("ITUB4"))
        uow.commit()
    profiled = client.put(
        f"/api/v1/assets/{asset_id}/checklist",
        json={
            "checklist_profile": "BANK",
            "cerrado_answers": {"basel": "YES", "npl": "YES"},
            "evidence": {"basel": "Basileia 13,5%"},
        },
    )
    assert profiled.status_code == 200, profiled.text

    analysis = client.get(f"/api/v1/assets/{asset_id}/analysis").json()
    assert [s["reference_date"][:4] for s in analysis["fundamental_history"]] == [
        "2020",
        "2021",
        "2022",
        "2023",
        "2024",
    ]
    metrics = analysis["historical_metrics"]
    assert metrics["years"] == 5 and metrics["always_profitable"] is True
    answers = {a["question_id"]: a for a in analysis["checklist"]["answers"]}
    assert answers["roe"]["source"] == "AUTO"
    assert answers["roe"]["evidence"].startswith("ROE médio")
    assert answers["profitable"]["evidence"] == "Lucro em 5 de 5 anos"
    assert answers["basel"]["evidence"] == "Basileia 13,5%"
    valuation = analysis["valuation"]
    assert valuation["profile"] == "BANK"
    methods = {m["method"]: m for m in valuation["methods"]}
    assert methods["JUSTIFIED_PB"]["value"] == pytest.approx(30.0)
    assert methods["BAZIN"]["value"] == pytest.approx(2.24 / 0.06, abs=0.01)
    assert len(analysis["checklist_history"]) == 1

    # The watchlist lists it with checklist and valuation; the screener marks it registered.
    watchlist = client.get("/api/v1/research/watchlist").json()
    assert [w["ticker"] for w in watchlist] == ["ITUB4"]
    assert watchlist[0]["checklist_profile"] == "BANK"
    assert watchlist[0]["valuation_verdict"] in {"DISCOUNTED", "FAIR"}
    registered = client.get("/api/v1/research/screener", params={"q": "itau"}).json()
    assert registered["results"][0]["asset_id"] == asset_id
    assert registered["results"][0]["lifecycle_status"] in {"WATCHLIST", "ELIGIBLE"}
    excluded = client.get(
        "/api/v1/research/screener", params={"q": "itau", "exclude_registered": True}
    ).json()
    assert excluded["results"] == []

    # Eligible under the policy, it receives contributions without being held yet.
    assert watchlist[0]["lifecycle_status"] == "ELIGIBLE"
    plan = client.post("/api/v1/portfolio/contribution", json={"amount_brl": 1000.0})
    assert plan.status_code == 200, plan.text
    orders = {o["ticker"]: o for o in plan.json()["orders"]}
    assert orders["ITUB4"]["allocated_amount_brl"] > 0

    # No position: removing deletes the asset for good.
    assert client.delete(f"/api/v1/research/watchlist/{asset_id}").status_code == 204
    assert client.get(f"/api/v1/assets/{asset_id}").status_code == 404
    assert client.get("/api/v1/research/watchlist").json() == []


def test_watchlist_requires_type_outside_the_catalog_and_protects_positions(
    research: SimpleNamespace,
) -> None:
    client = research.client
    unknown = client.post("/api/v1/research/watchlist", json={"ticker": "XPTO3"})
    assert unknown.status_code == 400
    assert unknown.json()["code"] == "UNKNOWN_INSTRUMENT"
    typed = client.post(
        "/api/v1/research/watchlist",
        json={"ticker": "XPTO3", "asset_type": "STOCK_BR", "name": "Xpto"},
    )
    assert typed.status_code == 201

    held = client.post("/api/v1/research/watchlist", json={"ticker": "WEGE3"}).json()
    trade = client.post(
        "/api/v1/transactions",
        json={
            "asset_id": held["asset_id"],
            "kind": "BUY",
            "trade_date": "2025-01-02",
            "quantity": "10",
            "unit_price": "40",
        },
    )
    assert trade.status_code == 201, trade.text
    blocked = client.delete(f"/api/v1/research/watchlist/{held['asset_id']}")
    assert blocked.status_code == 409
    assert [w["ticker"] for w in client.get("/api/v1/research/watchlist").json()] == ["XPTO3"]
    cash = client.post("/api/v1/assets", json={"name": "Caixa", "asset_type": "CASH"})
    assert cash.status_code == 201
    # Cash and fixed income are not market instruments to follow.
    assert [w["ticker"] for w in client.get("/api/v1/research/watchlist").json()] == ["XPTO3"]


def test_below_band_shortcut_without_positions_returns_nothing(research: SimpleNamespace) -> None:
    body = research.client.get("/api/v1/research/screener", params={"below_band": True}).json()
    assert body["results"] == []
    assert body["catalog_size"] == 7


def test_follow_picks_the_arca_quadrant_and_fetches_the_statements(
    research: SimpleNamespace,
) -> None:
    client = research.client
    with research.uow_factory() as uow:
        assert uow.fundamentals.list_for_many(["ITUB4"]) == {}

    # The suggestion is used when no quadrant is chosen...
    suggested = client.post("/api/v1/research/watchlist", json={"ticker": "BBAS3"})
    assert suggested.status_code == 201, suggested.text
    assert suggested.json()["arca_class"] == "ACOES"

    # ...and the chosen one otherwise.
    chosen = client.post(
        "/api/v1/research/watchlist",
        json={"ticker": "ITUB4", "arca_class": "ATIVOS_INTERNACIONAIS"},
    )
    assert chosen.status_code == 201, chosen.text
    assert chosen.json()["arca_class"] == "ATIVOS_INTERNACIONAIS"

    # The yearly statements were fetched right after it was registered (background task).
    with research.uow_factory() as uow:
        assert uow.fundamentals.list_for_many(["ITUB4"])["ITUB4"]

    asset_id = chosen.json()["asset_id"]
    moved = client.put(
        f"/api/v1/research/watchlist/{asset_id}/classification", json={"arca_class": "ACOES"}
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["arca_class"] == "ACOES"
    listed = {w["ticker"]: w["arca_class"] for w in client.get("/api/v1/research/watchlist").json()}
    assert listed == {"BBAS3": "ACOES", "ITUB4": "ACOES"}

    missing = client.put(
        "/api/v1/research/watchlist/9999/classification", json={"arca_class": "ACOES"}
    )
    assert missing.status_code == 404
    invalid = client.put(
        f"/api/v1/research/watchlist/{asset_id}/classification", json={"arca_class": "GOLD"}
    )
    assert invalid.status_code == 422
