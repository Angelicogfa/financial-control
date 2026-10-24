"""Integration tests for /portfolio/analytics (findings C-03 and I-09)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from fincontrol_core.domain.entities import PortfolioSnapshotEntity
from fincontrol_core.domain.enums import SeriesUnit

DAYS = [date(2025, 1, d) for d in (2, 3, 6, 7)]
URL = "/api/v1/portfolio/analytics?date_from=2025-01-01&date_to=2025-01-31"


def _seed_ibov(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        uow.market_series.upsert_points(
            "IBOV",
            list(zip(DAYS, [120_000.0, 121_200.0, 119_988.0, 121_188.0], strict=True)),
            unit=SeriesUnit.INDEX_POINTS,
        )
        uow.commit()


def test_without_history_only_benchmarks_are_returned(api: SimpleNamespace) -> None:
    _seed_ibov(api)

    body = api.client.get(URL).json()

    assert body["status"] == "INSUFFICIENT_HISTORY"
    assert body["available_points"] == 0
    assert "PORTFOLIO" not in body["curves"]
    assert "IBOV" in body["curves"]
    assert body["summary"]["observations"] == 0


def test_with_history_portfolio_curve_and_aligned_benchmarks(api: SimpleNamespace) -> None:
    _seed_ibov(api)
    values = [10_000.0, 10_100.0, 10_200.0, 10_302.0]
    with api.uow_factory() as uow:
        for day, value in zip(DAYS, values, strict=True):
            uow.snapshots.upsert(
                PortfolioSnapshotEntity(
                    snapshot_date=day,
                    invested_value=10_000.0,
                    market_value=value,
                    unrealized_pnl=value - 10_000.0,
                )
            )
        uow.commit()

    body = api.client.get(URL).json()

    assert body["status"] == "OK"
    assert body["available_points"] == 4
    portfolio = body["curves"]["PORTFOLIO"]
    assert portfolio[0] == {"date": "2025-01-02", "value": 100.0}
    assert portfolio[-1]["value"] == 103.02
    assert body["summary"]["observations"] == 3
    ibov = next(b for b in body["summary"]["benchmarks"] if b["benchmark"] == "IBOV")
    assert ibov["benchmark_return"] == round(121_188.0 / 120_000.0 - 1, 4)
    assert body["correlation_matrix"]["PORTFOLIO"]["PORTFOLIO"] == 1.0
