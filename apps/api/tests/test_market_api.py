"""Integration test for GET /market/series-status."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from core.helpers.calendar import previous_business_day
from domain.shared.enums import SeriesUnit


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


def test_job_runs_lists_latest_execution_per_job(api: SimpleNamespace) -> None:
    from datetime import UTC, datetime

    from domain.shared.entities import JobRunEntity
    from domain.shared.enums import JobRunStatus

    with api.uow_factory() as uow:
        for status in (JobRunStatus.FAILED, JobRunStatus.SUCCESS):
            uow.job_runs.add(
                JobRunEntity(
                    job_name="sync_bcb_and_benchmarks",
                    started_at=datetime(2025, 1, 2, tzinfo=UTC),
                    status=status,
                    attempts=1,
                    details={"CDI": 2},
                )
            )
        uow.commit()

    (run,) = api.client.get("/api/v1/market/job-runs").json()

    assert run["job_name"] == "sync_bcb_and_benchmarks"
    assert run["status"] == "SUCCESS"
    assert run["details"] == {"CDI": 2}
