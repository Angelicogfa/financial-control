"""Integration tests for ledger integrity: edits, deletions and FX rules (findings I-04, C-02)."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient


def _asset(client: TestClient, ticker: str, asset_type: str = "STOCK_BR") -> int:
    resp = client.post(
        "/api/v1/assets", json={"ticker": ticker, "name": ticker, "asset_type": asset_type}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _trade(client: TestClient, asset_id: int, kind: str, on: str, qty: str, **extra) -> dict:
    payload = {
        "asset_id": asset_id,
        "kind": kind,
        "trade_date": on,
        "quantity": qty,
        "unit_price": "40.00",
        **extra,
    }
    return client.post("/api/v1/transactions", json=payload).json()


def test_editing_a_buy_below_later_sells_is_a_conflict(api: SimpleNamespace) -> None:
    asset_id = _asset(api.client, "WEGE3")
    buy = _trade(api.client, asset_id, "BUY", "2025-01-02", "100")
    _trade(api.client, asset_id, "SELL", "2025-02-03", "60")

    resp = api.client.put(
        f"/api/v1/transactions/{buy['id']}",
        json={"kind": "BUY", "trade_date": "2025-01-02", "quantity": "50", "unit_price": "40"},
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "LEDGER_CONFLICT"


def test_editing_a_transaction_updates_the_position(api: SimpleNamespace) -> None:
    asset_id = _asset(api.client, "WEGE3")
    buy = _trade(api.client, asset_id, "BUY", "2025-01-02", "100")

    resp = api.client.put(
        f"/api/v1/transactions/{buy['id']}",
        json={"kind": "BUY", "trade_date": "2025-01-03", "quantity": "120", "unit_price": "41"},
    )

    assert resp.status_code == 200
    assert resp.json()["quantity"] == 120.0
    position = api.client.get("/api/v1/portfolio").json()["positions"][0]
    assert position["quantity"] == 120.0
    assert position["invested_value_brl"] == 4920.0


def test_deleting_unknown_transaction_is_not_found(api: SimpleNamespace) -> None:
    resp = api.client.delete("/api/v1/transactions/999")
    assert resp.status_code == 404


def test_deleting_a_sell_is_allowed(api: SimpleNamespace) -> None:
    asset_id = _asset(api.client, "WEGE3")
    _trade(api.client, asset_id, "BUY", "2025-01-02", "100")
    sell = _trade(api.client, asset_id, "SELL", "2025-02-03", "60")

    assert api.client.delete(f"/api/v1/transactions/{sell['id']}").status_code == 204


def test_usd_asset_requires_trade_and_payment_fx(api: SimpleNamespace) -> None:
    asset_id = _asset(api.client, "AAPL", "STOCK_INTL")

    missing_fx = api.client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "kind": "BUY",
            "trade_date": "2025-01-02",
            "quantity": "1",
            "unit_price": "200",
        },
    )
    assert missing_fx.status_code == 400
    assert missing_fx.json()["code"] == "FX_RATE_REQUIRED"

    ok = _trade(api.client, asset_id, "BUY", "2025-01-02", "1", fx_rate="5.8")
    assert ok["total_brl"] == 232.0

    earning = api.client.post(
        "/api/v1/earnings",
        json={
            "asset_id": asset_id,
            "kind": "DIVIDEND",
            "payment_date": "2025-02-14",
            "gross_amount": "1.00",
            "withholding_tax": "0.30",
            "fx_rate": "5.9",
        },
    )
    assert earning.status_code == 201
    assert earning.json()["net_amount_brl"] == 4.13


def test_editing_an_earning(api: SimpleNamespace) -> None:
    asset_id = _asset(api.client, "HGLG11", "FII")
    created = api.client.post(
        "/api/v1/earnings",
        json={
            "asset_id": asset_id,
            "kind": "FII_YIELD",
            "payment_date": "2025-02-14",
            "gross_amount": "11.00",
        },
    ).json()

    resp = api.client.put(
        f"/api/v1/earnings/{created['id']}",
        json={"kind": "FII_YIELD", "payment_date": "2025-02-14", "gross_amount": "12.50"},
    )

    assert resp.status_code == 200
    assert resp.json()["net_amount"] == 12.5
    assert (
        api.client.put(
            "/api/v1/earnings/999",
            json={"kind": "FII_YIELD", "payment_date": "2025-02-14", "gross_amount": "1"},
        ).status_code
        == 404
    )


def test_fixed_income_redemption_above_value_is_rejected(api: SimpleNamespace) -> None:
    resp = api.client.post(
        "/api/v1/assets",
        json={
            "ticker": "CDB-PRE",
            "name": "CDB Pre 12%",
            "asset_type": "FIXED_INCOME",
            "fixed_income_term": {
                "instrument_kind": "CDB",
                "indexer": "PRE",
                "contracted_rate": "0.12",
                "issue_date": "2025-01-02",
            },
        },
    )
    asset_id = resp.json()["id"]
    api.client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "kind": "BUY",
            "trade_date": "2025-01-02",
            "quantity": "1",
            "unit_price": "1000",
        },
    )

    oversell = api.client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "kind": "SELL",
            "trade_date": "2025-02-03",
            "quantity": "1",
            "unit_price": "5000",
        },
    )

    assert oversell.status_code == 400
    assert oversell.json()["code"] == "INSUFFICIENT_QUANTITY"
