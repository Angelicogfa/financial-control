"""Integration test for GET /market/series-status."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from fincontrol_core.calendar import previous_business_day
from fincontrol_core.domain.enums import SeriesUnit


def test_series_status_reports_every_tracked_series(api: SimpleNamespace) -> None:
    last = previous_business_day(date.today())
    with api.uow_factory() as uow:
        uow.market_series.upsert_points("CDI", [(last, 0.055)], unit=SeriesUnit.PERCENT_PER_DAY)
        uow.market_series.upsert_points(
            "IBOV", [(date.today() - timedelta(days=30), 120_000.0)], unit=SeriesUnit.INDEX_POINTS
        )
        uow.commit()

    body = {row["symbol"]: row for row in api.client.get("/api/v1/market/series-status").json()}

    assert list(body) == ["CDI", "SELIC", "IPCA", "IBOV", "IFIX", "SP500"]
    assert body["CDI"]["stale"] is False
    assert body["CDI"]["unit"] == "PERCENT_PER_DAY"
    assert body["IBOV"]["stale"] is True
    assert body["SELIC"] == {
        "symbol": "SELIC",
        "unit": None,
        "points": 0,
        "first_date": None,
        "last_date": None,
        "stale": True,
        "missing_business_days": 0,
    }
