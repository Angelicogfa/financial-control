"""Phase 12 acceptance: import a B3 statement, confirm a contribution and see positions,
allocation and alerts updated without typing a single trade."""

from __future__ import annotations

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

FIXTURES = Path(__file__).parent / "fixtures"
PRICES = {"ITSA4": 10.0, "HGLG11": 158.0, "WEGE3": 26.0}


class _NoYahoo:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.info: dict[str, Any] = {}

    def history(self, period: str = "1y", interval: str = "1d") -> Any:
        import pandas as pd

        return pd.DataFrame()


def _brapi(request: httpx.Request) -> httpx.Response:
    ticker = request.url.path.rstrip("/").rsplit("/", 1)[-1]
    if ticker not in PRICES:
        return httpx.Response(404)
    return httpx.Response(
        200, json={"results": [{"symbol": ticker, "regularMarketPrice": PRICES[ticker]}]}
    )


@pytest.fixture
def client(api: SimpleNamespace):  # type: ignore[no-untyped-def]
    gateway = CachedMarketGateway(
        brapi=BrapiProvider(client=httpx.Client(transport=httpx.MockTransport(_brapi))),
        yfinance=YFinanceProvider(ticker_factory=_NoYahoo),
        bcb=BcbSgsProvider(
            client=httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(500)))
        ),
        cache=InMemoryCache(),
    )
    api.app.dependency_overrides[get_market_gateway] = lambda: gateway
    return api.client


def _import(client, name: str, **form: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/imports/b3/commit",
        files={"file": (name, (FIXTURES / name).read_bytes())},
        data=form,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_import_contribute_and_follow_alerts(client) -> None:  # type: ignore[no-untyped-def]
    _import(client, "b3_negociacao.csv", create_tickers="ITSA4,HGLG11,WEGE3")
    _import(client, "b3_movimentacao.csv")

    before = client.get("/api/v1/portfolio/consolidated").json()
    allocations = {a["arca_class"]: a for a in before["allocations"]}
    assert allocations["CAIXA"]["band_status"] == "BELOW"

    alerts = client.get("/api/v1/alerts").json()
    keys = {a["key"] for a in alerts["alerts"]}
    assert "band:CAIXA:BELOW" in keys
    assert any(k.startswith("series:CDI") for k in keys)  # BCB never synced in tests
    assert alerts["alerts"][0]["severity"] in {"CRITICAL", "WARNING"}

    hide = client.post("/api/v1/alerts/dismissals", json={"key": "band:CAIXA:BELOW", "days": 3})
    assert hide.status_code == 204
    hidden = client.get("/api/v1/alerts").json()
    assert "band:CAIXA:BELOW" not in {a["key"] for a in hidden["alerts"]}
    assert hidden["dismissed"] == 1
    client.delete("/api/v1/alerts/dismissals", params={"key": "band:CAIXA:BELOW"})
    assert "band:CAIXA:BELOW" in {a["key"] for a in client.get("/api/v1/alerts").json()["alerts"]}

    # Below-band classes without eligible assets keep the money unallocated.
    idle = client.post("/api/v1/contributions", json={"amount_brl": 1000.0}).json()
    assert idle["plan"]["unallocated_cash_brl"] == pytest.approx(1000.0)
    client.post(f"/api/v1/contributions/{idle['id']}/discard")
    cash = client.post(
        "/api/v1/assets",
        json={"name": "Reserva corretora", "asset_type": "CASH", "manual_price": "1"},
    )
    assert cash.status_code == 201, cash.text

    plan = client.post("/api/v1/contributions", json={"amount_brl": 1000.0}).json()
    confirmed = client.post(
        f"/api/v1/contributions/{plan['id']}/confirm", json={"trade_date": "2026-01-05"}
    )
    assert confirmed.status_code == 200, confirmed.text

    after = client.get("/api/v1/portfolio/consolidated").json()
    assert after["total_invested_brl"] > before["total_invested_brl"]
    invested_after = {a["arca_class"]: a["invested_value"] for a in after["allocations"]}
    invested_before = {a["arca_class"]: a["invested_value"] for a in before["allocations"]}
    grown = {c for c in invested_after if invested_after[c] > invested_before[c]}
    assert grown == {"CAIXA"}
    assert "band:CAIXA:BELOW" not in {
        a["key"] for a in client.get("/api/v1/alerts").json()["alerts"]
    }
