"""Ledger changes drop the snapshots from their date on so the backfill rebuilds them."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from domain.portfolio.services.snapshots import invalidate_snapshots_from
from domain.shared.entities import PortfolioSnapshotEntity

DAYS = [date(2025, 3, d) for d in (3, 4, 5, 6, 7)]


def _seed_snapshots(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        for day in DAYS:
            uow.snapshots.upsert(
                PortfolioSnapshotEntity(
                    snapshot_date=day, invested_value=1.0, market_value=1.0, unrealized_pnl=0.0
                )
            )
        uow.commit()


def _snapshot_days(api: SimpleNamespace) -> list[date]:
    with api.uow_factory() as uow:
        return [s.snapshot_date for s in uow.snapshots.list_range()]


def _asset(api: SimpleNamespace, ticker: str, asset_type: str = "STOCK_BR") -> int:
    resp = api.client.post(
        "/api/v1/assets", json={"ticker": ticker, "name": ticker, "asset_type": asset_type}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _buy(api: SimpleNamespace, asset_id: int, on: str) -> dict:
    resp = api.client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "kind": "BUY",
            "trade_date": on,
            "quantity": "10",
            "unit_price": "20",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_helper_deletes_from_the_earliest_date() -> None:
    uow = MagicMock()
    uow.snapshots.delete_range.return_value = 3

    assert invalidate_snapshots_from(uow, date(2025, 3, 6), None, date(2025, 3, 4)) == 3
    uow.snapshots.delete_range.assert_called_once_with(date_from=date(2025, 3, 4))


def test_helper_without_dates_keeps_everything() -> None:
    uow = MagicMock()

    assert invalidate_snapshots_from(uow) == 0
    assert invalidate_snapshots_from(uow, None) == 0
    uow.snapshots.delete_range.assert_not_called()


def test_backdated_trade_drops_snapshots_from_its_date(api: SimpleNamespace) -> None:
    asset_id = _asset(api, "WEGE3")
    _seed_snapshots(api)

    _buy(api, asset_id, "2025-03-05")

    assert _snapshot_days(api) == DAYS[:2]


def test_editing_a_trade_uses_the_earlier_of_old_and_new_dates(api: SimpleNamespace) -> None:
    asset_id = _asset(api, "WEGE3")
    trade = _buy(api, asset_id, "2025-03-06")
    _seed_snapshots(api)

    resp = api.client.put(
        f"/api/v1/transactions/{trade['id']}",
        json={"kind": "BUY", "trade_date": "2025-03-07", "quantity": "10", "unit_price": "21"},
    )

    assert resp.status_code == 200
    assert _snapshot_days(api) == DAYS[:3]


def test_deleting_a_trade_drops_snapshots_from_its_date(api: SimpleNamespace) -> None:
    asset_id = _asset(api, "WEGE3")
    trade = _buy(api, asset_id, "2025-03-04")
    _seed_snapshots(api)

    assert api.client.delete(f"/api/v1/transactions/{trade['id']}").status_code == 204
    assert _snapshot_days(api) == DAYS[:1]


def test_rejected_trade_keeps_snapshots(api: SimpleNamespace) -> None:
    asset_id = _asset(api, "WEGE3")
    _seed_snapshots(api)

    oversell = api.client.post(
        "/api/v1/transactions",
        json={
            "asset_id": asset_id,
            "kind": "SELL",
            "trade_date": "2025-03-03",
            "quantity": "10",
            "unit_price": "20",
        },
    )

    assert oversell.status_code == 400
    assert _snapshot_days(api) == DAYS


def test_earning_changes_drop_snapshots_from_the_payment_date(api: SimpleNamespace) -> None:
    asset_id = _asset(api, "HGLG11", "FII")
    _seed_snapshots(api)

    created = api.client.post(
        "/api/v1/earnings",
        json={
            "asset_id": asset_id,
            "kind": "FII_YIELD",
            "payment_date": "2025-03-07",
            "gross_amount": "11.00",
        },
    ).json()
    assert _snapshot_days(api) == DAYS[:4]

    api.client.put(
        f"/api/v1/earnings/{created['id']}",
        json={"kind": "FII_YIELD", "payment_date": "2025-03-06", "gross_amount": "12.50"},
    )
    assert _snapshot_days(api) == DAYS[:3]

    _seed_snapshots(api)
    assert api.client.delete(f"/api/v1/earnings/{created['id']}").status_code == 204
    assert _snapshot_days(api) == DAYS[:3]
    assert api.client.delete("/api/v1/earnings/999").status_code == 404


def test_corporate_events_drop_snapshots_from_the_ex_date(api: SimpleNamespace) -> None:
    asset_id = _asset(api, "WEGE3")
    _buy(api, asset_id, "2025-01-02")
    _seed_snapshots(api)

    event = api.client.post(
        "/api/v1/corporate-events",
        json={"asset_id": asset_id, "kind": "SPLIT", "ex_date": "2025-03-06", "factor": "2"},
    ).json()
    assert _snapshot_days(api) == DAYS[:3]

    _seed_snapshots(api)
    assert api.client.delete(f"/api/v1/corporate-events/{event['id']}").status_code == 204
    assert _snapshot_days(api) == DAYS[:3]


def test_daily_job_backfills_before_recording_today(monkeypatch) -> None:
    from worker import jobs

    calls: list[str] = []
    monkeypatch.setattr(jobs, "backfill_snapshots_job", lambda *_: calls.append("backfill"))
    monkeypatch.setattr(
        jobs, "record_daily_snapshot_job", lambda *_: calls.append("record") or "today"
    )

    assert jobs.backfill_and_record_snapshot_job(MagicMock(), MagicMock()) == "today"
    assert calls == ["backfill", "record"]
