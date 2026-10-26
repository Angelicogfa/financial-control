"""API tests for the series the analytics home reads (phase 13 support)."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from domain.shared.entities import PortfolioSnapshotEntity
from domain.shared.enums import SeriesUnit


def test_snapshots_and_cdi_curve(api: SimpleNamespace) -> None:
    start = date.today() - timedelta(days=10)
    with api.uow_factory() as uow:
        for offset, value in ((0, 1000.0), (1, 1010.0), (2, 1030.0)):
            uow.snapshots.upsert(
                PortfolioSnapshotEntity(
                    snapshot_date=start + timedelta(days=offset),
                    invested_value=1000.0,
                    market_value=value,
                    unrealized_pnl=value - 1000.0,
                    consolidated_pnl=value - 1000.0,
                )
            )
        uow.market_series.upsert_points(
            "CDI",
            [(start + timedelta(days=d), 0.04) for d in range(3)],
            unit=SeriesUnit.PERCENT_PER_DAY,
        )
        uow.commit()

    points = api.client.get("/api/v1/portfolio/snapshots").json()
    assert [p["market_value"] for p in points] == [1000.0, 1010.0, 1030.0]
    since = api.client.get(
        "/api/v1/portfolio/snapshots", params={"date_from": str(start + timedelta(days=2))}
    ).json()
    assert len(since) == 1

    analytics = api.client.get("/api/v1/portfolio/analytics").json()
    assert [p["value"] for p in analytics["curves"]["CDI"]] == [100.0, 100.04, 100.08]
    assert analytics["curves"]["PORTFOLIO"][-1]["value"] == 103.0


def test_single_trade_and_earning_can_be_read(api: SimpleNamespace) -> None:
    client = api.client
    asset = client.post(
        "/api/v1/assets", json={"ticker": "ITSA4", "name": "Itausa", "asset_type": "STOCK_BR"}
    ).json()
    trade = client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset["id"],
            "kind": "BUY",
            "trade_date": "2025-01-02",
            "quantity": "10",
            "unit_price": "9.5",
        },
    ).json()
    earning = client.post(
        "/api/v1/earnings",
        json={
            "asset_id": asset["id"],
            "kind": "DIVIDEND",
            "payment_date": "2025-03-01",
            "gross_amount": "1.5",
        },
    ).json()
    assert client.get(f"/api/v1/transactions/{trade['id']}").json()["ticker"] == "ITSA4"
    assert client.get(f"/api/v1/earnings/{earning['id']}").json()["kind"] == "DIVIDEND"
    assert client.get("/api/v1/transactions/999").status_code == 404
    assert client.get("/api/v1/earnings/999").status_code == 404
