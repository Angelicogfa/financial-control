"""Integration tests for custody accounts and generated fixed income codes (item 10.5)."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient


def _stock(client: TestClient, ticker: str) -> int:
    resp = client.post(
        "/api/v1/assets", json={"ticker": ticker, "name": ticker, "asset_type": "STOCK_BR"}
    )
    return resp.json()["id"]


def _buy(client: TestClient, asset_id: int, qty: str, account_id: int | None = None) -> dict:
    payload = {
        "asset_id": asset_id,
        "kind": "BUY",
        "trade_date": "2025-01-02",
        "quantity": qty,
        "unit_price": "10",
    }
    if account_id is not None:
        payload["account_id"] = account_id
    return client.post("/api/v1/transactions", json=payload).json()


def test_principal_account_exists_and_is_default(api: SimpleNamespace) -> None:
    accounts = api.client.get("/api/v1/accounts").json()
    assert [a["name"] for a in accounts] == ["Principal"]

    tx = _buy(api.client, _stock(api.client, "WEGE3"), "10")
    assert tx["account_id"] == accounts[0]["id"]


def test_accounts_split_ledger_and_portfolio(api: SimpleNamespace) -> None:
    xp = api.client.post(
        "/api/v1/accounts", json={"name": "XP", "institution": "XP Investimentos"}
    ).json()
    asset_id = _stock(api.client, "WEGE3")
    _buy(api.client, asset_id, "10")
    _buy(api.client, asset_id, "30", account_id=xp["id"])

    in_xp = api.client.get("/api/v1/transactions", params={"account_id": xp["id"]}).json()
    portfolio_xp = api.client.get("/api/v1/portfolio", params={"account_id": xp["id"]}).json()
    portfolio_all = api.client.get("/api/v1/portfolio").json()

    assert in_xp["meta"]["total_items"] == 1
    assert portfolio_xp["positions"][0]["quantity"] == 30.0
    assert portfolio_all["positions"][0]["quantity"] == 40.0


def test_account_rules(api: SimpleNamespace) -> None:
    dup = api.client.post("/api/v1/accounts", json={"name": "Principal"})
    assert dup.status_code == 409

    principal = api.client.get("/api/v1/accounts").json()[0]
    last = api.client.put(
        f"/api/v1/accounts/{principal['id']}", json={"name": "Principal", "is_active": False}
    )
    assert last.json()["code"] == "LAST_ACTIVE_ACCOUNT"

    old = api.client.post("/api/v1/accounts", json={"name": "Antiga", "kind": "BANK"}).json()
    api.client.put(f"/api/v1/accounts/{old['id']}", json={"name": "Antiga", "is_active": False})
    rejected = api.client.post(
        "/api/v1/transactions",
        json={
            "asset_id": _stock(api.client, "ITUB4"),
            "kind": "BUY",
            "trade_date": "2025-01-02",
            "quantity": "1",
            "unit_price": "10",
            "account_id": old["id"],
        },
    )
    assert rejected.json()["code"] == "INACTIVE_ACCOUNT"
    assert api.client.get("/api/v1/portfolio", params={"account_id": 999}).status_code == 404


def test_fixed_income_gets_generated_unique_code(api: SimpleNamespace) -> None:
    term = {
        "instrument_kind": "CDB",
        "indexer": "CDI",
        "contracted_rate": "1.10",
        "issue_date": "2025-01-02",
        "maturity_date": "2027-01-15",
        "issuer": "Banco Inter",
    }
    body = {"name": "CDB Inter 110%", "asset_type": "FIXED_INCOME", "fixed_income_term": term}

    first = api.client.post("/api/v1/assets", json=body).json()
    second = api.client.post("/api/v1/assets", json=body).json()
    stock = api.client.post("/api/v1/assets", json={"name": "WEG", "asset_type": "STOCK_BR"})

    assert first["ticker"] == "CDB-BANCOINTER-20270115"
    assert second["ticker"] == "CDB-BANCOINTER-20270115-2"
    assert stock.json()["code"] == "TICKER_REQUIRED"
