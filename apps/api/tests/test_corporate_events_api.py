"""API tests for corporate events and their effect on positions (item 12.4)."""

from __future__ import annotations

from types import SimpleNamespace


def test_split_enables_sale_and_protects_the_ledger(api: SimpleNamespace) -> None:
    client = api.client
    asset = client.post(
        "/api/v1/assets",
        json={"ticker": "WEGE3", "name": "WEG", "asset_type": "STOCK_BR", "manual_price": "25"},
    ).json()
    asset_id = asset["id"]
    bought = client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "kind": "BUY",
            "trade_date": "2024-01-02",
            "quantity": "100",
            "unit_price": "40",
        },
    )
    assert bought.status_code == 201

    oversell = {
        "asset_id": asset_id,
        "kind": "SELL",
        "trade_date": "2024-07-01",
        "quantity": "150",
        "unit_price": "25",
    }
    assert client.post("/api/v1/transactions", json=oversell).status_code == 400

    split = client.post(
        "/api/v1/corporate-events",
        json={"asset_id": asset_id, "kind": "SPLIT", "ex_date": "2024-06-03", "factor": "2"},
    )
    assert split.status_code == 201, split.text
    event = split.json()
    assert (event["ticker"], event["imported"]) == ("WEGE3", False)
    assert client.post("/api/v1/transactions", json=oversell).status_code == 201

    position = next(
        p
        for p in client.get("/api/v1/portfolio/consolidated").json()["positions"]
        if p["ticker"] == "WEGE3"
    )
    assert position["quantity"] == 50
    assert position["average_price"] == 20

    blocked = client.delete(f"/api/v1/corporate-events/{event['id']}")
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "LEDGER_CONFLICT"

    listed = client.get("/api/v1/corporate-events", params={"asset_id": asset_id}).json()
    assert [e["kind"] for e in listed] == ["SPLIT"]
    assert client.delete("/api/v1/corporate-events/999").status_code == 404


def test_invalid_events_are_rejected(api: SimpleNamespace) -> None:
    client = api.client
    asset_id = client.post(
        "/api/v1/assets", json={"ticker": "ITSA4", "name": "Itausa", "asset_type": "STOCK_BR"}
    ).json()["id"]
    wrong_factor = client.post(
        "/api/v1/corporate-events",
        json={
            "asset_id": asset_id,
            "kind": "REVERSE_SPLIT",
            "ex_date": "2024-01-02",
            "factor": "2",
        },
    )
    assert wrong_factor.status_code == 400
    bonus = client.post(
        "/api/v1/corporate-events",
        json={
            "asset_id": asset_id,
            "kind": "BONUS",
            "ex_date": "2024-01-02",
            "factor": "1.1",
            "unit_cost": "18.5",
        },
    )
    assert bonus.status_code == 201
    assert (
        client.post(
            "/api/v1/corporate-events",
            json={"asset_id": 999, "kind": "SPLIT", "ex_date": "2024-01-02", "factor": "2"},
        ).status_code
        == 404
    )
