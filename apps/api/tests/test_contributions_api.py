"""API tests for persisted contribution plans: draft, confirm into trades, discard (12.1)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from composition import get_market_gateway
from infra.cache.redis_cache import InMemoryCache
from infra.providers.bcb import BcbSgsProvider
from infra.providers.brapi import BrapiProvider
from infra.providers.gateway import CachedMarketGateway
from infra.providers.yfinance_provider import YFinanceProvider

PRICES = {"ITUB4": 32.0, "HGLG11": 155.0}


class _NoYahoo:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.info: dict[str, object] = {}

    def history(self, period: str = "1y", interval: str = "1d") -> object:
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
    for ticker, asset_type in (("ITUB4", "STOCK_BR"), ("HGLG11", "FII")):
        created = api.client.post(
            "/api/v1/assets", json={"ticker": ticker, "name": ticker, "asset_type": asset_type}
        )
        assert created.status_code == 201, created.text
    return api.client


def test_draft_is_confirmed_into_trades_once(client) -> None:  # type: ignore[no-untyped-def]
    draft = client.post("/api/v1/contributions", json={"amount_brl": 2000.0})
    assert draft.status_code == 201, draft.text
    body = draft.json()
    assert body["status"] == "DRAFT"
    plan_id = body["id"]
    orders = [o for o in body["plan"]["orders"] if o["recommended_quantity"] > 0]
    assert {o["ticker"] for o in orders} == {"ITUB4", "HGLG11"}

    confirmed = client.post(
        f"/api/v1/contributions/{plan_id}/confirm", json={"trade_date": "2026-01-05"}
    )
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()
    assert result["status"] == "CONFIRMED"
    assert result["account_id"] is None or result["account_id"] == 1
    assert len(result["transaction_ids"]) == len(orders)

    trades = client.get("/api/v1/transactions", params={"page_size": 50}).json()["items"]
    assert {t["notes"] for t in trades} == {f"Aporte #{plan_id}"}
    by_ticker = {t["ticker"]: t for t in trades}
    itub_order = next(o for o in orders if o["ticker"] == "ITUB4")
    assert float(by_ticker["ITUB4"]["quantity"]) == itub_order["recommended_quantity"]
    assert float(by_ticker["ITUB4"]["unit_price"]) == pytest.approx(32.0)

    again = client.post(
        f"/api/v1/contributions/{plan_id}/confirm", json={"trade_date": "2026-01-05"}
    )
    assert again.status_code == 409
    assert again.json()["code"] == "PLAN_NOT_DRAFT"

    portfolio = client.get("/api/v1/portfolio/consolidated").json()
    assert portfolio["total_invested_brl"] == pytest.approx(
        sum(float(t["quantity"]) * float(t["unit_price"]) for t in trades)
    )


def test_custom_executions_and_discard(client) -> None:  # type: ignore[no-untyped-def]
    plan = client.post("/api/v1/contributions", json={"amount_brl": 1000.0}).json()
    itub = next(o for o in plan["plan"]["orders"] if o["ticker"] == "ITUB4")
    outside = client.post(
        f"/api/v1/contributions/{plan['id']}/confirm",
        json={
            "trade_date": "2026-01-06",
            "executions": [{"asset_id": 999, "quantity": "1", "unit_price": "10"}],
        },
    )
    assert outside.status_code == 400
    assert outside.json()["code"] == "ASSET_NOT_IN_PLAN"

    custom = client.post(
        f"/api/v1/contributions/{plan['id']}/confirm",
        json={
            "trade_date": "2026-01-06",
            "account_id": 1,
            "executions": [
                {"asset_id": itub["asset_id"], "quantity": "7", "unit_price": "31.5", "fees": "1"}
            ],
        },
    )
    assert custom.status_code == 200, custom.text
    trade_id = custom.json()["transaction_ids"][0]
    trades = client.get("/api/v1/transactions", params={"page_size": 50}).json()["items"]
    trade = next(t for t in trades if t["id"] == trade_id)
    assert trade["account_id"] == 1
    assert (float(trade["quantity"]), float(trade["unit_price"]), float(trade["fees"])) == (
        7.0,
        31.5,
        1.0,
    )

    other = client.post("/api/v1/contributions", json={"amount_brl": 500.0}).json()
    discarded = client.post(f"/api/v1/contributions/{other['id']}/discard")
    assert discarded.json()["status"] == "DISCARDED"
    assert discarded.json()["discarded_at"] is not None
    late = client.post(
        f"/api/v1/contributions/{other['id']}/confirm", json={"trade_date": "2026-01-06"}
    )
    assert late.status_code == 409

    listed = client.get("/api/v1/contributions").json()
    assert [p["status"] for p in listed] == ["DISCARDED", "CONFIRMED"]
    assert [p["id"] for p in client.get("/api/v1/contributions?status=DRAFT").json()] == []
    assert client.get("/api/v1/contributions/12345").status_code == 404


def test_foreign_execution_without_fx_is_read_in_brl() -> None:
    from decimal import Decimal

    from controllers.contributions.requests import ExecutionDTO
    from domain.contributions.services.use_cases import _execution

    brl_priced = _execution(
        ExecutionDTO(asset_id=1, quantity="2", unit_price="1000", fees="5"), Decimal("5")
    )
    assert (brl_priced.unit_price, brl_priced.fees, brl_priced.fx_rate) == (
        Decimal("200"),
        Decimal("1"),
        Decimal("5"),
    )
    explicit = _execution(
        ExecutionDTO(asset_id=1, quantity="2", unit_price="190", fx_rate="5.2"), Decimal("5")
    )
    assert (explicit.unit_price, explicit.fx_rate) == (Decimal("190"), Decimal("5.2"))
    domestic = _execution(ExecutionDTO(asset_id=1, quantity="2", unit_price="30"), None)
    assert domestic.fx_rate == Decimal("1")
