"""Unit tests for market series freshness diagnostics."""

from __future__ import annotations

from datetime import date

from fincontrol_core.domain.entities import MarketSeriesPoint
from fincontrol_core.domain.enums import SeriesUnit
from fincontrol_core.market.series_status import evaluate_series_status


def _points(symbol: str, unit: SeriesUnit, *days: date) -> list[MarketSeriesPoint]:
    return [MarketSeriesPoint(symbol, d, 1.0, unit=unit) for d in days]


def test_empty_series_is_stale() -> None:
    status = evaluate_series_status("CDI", [], date(2025, 6, 30))
    assert status.stale and status.points == 0 and status.last_date is None


def test_daily_rate_tolerates_one_day_publication_lag_and_counts_gaps() -> None:
    # Business days Jun 23-27 2025; Jun 25 is missing.
    days = (date(2025, 6, 23), date(2025, 6, 24), date(2025, 6, 26), date(2025, 6, 27))
    points = _points("CDI", SeriesUnit.PERCENT_PER_DAY, *days)

    fresh = evaluate_series_status("CDI", points, date(2025, 6, 30))
    stale = evaluate_series_status("CDI", points, date(2025, 7, 2))

    assert not fresh.stale
    assert stale.stale
    assert fresh.missing_business_days == 1


def test_monthly_and_index_staleness() -> None:
    ipca = _points("IPCA", SeriesUnit.PERCENT_PER_MONTH, date(2025, 4, 1))
    assert not evaluate_series_status("IPCA", ipca, date(2025, 6, 10)).stale
    assert evaluate_series_status("IPCA", ipca, date(2025, 7, 10)).stale

    ibov = _points("IBOV", SeriesUnit.INDEX_POINTS, date(2025, 6, 20))
    assert not evaluate_series_status("IBOV", ibov, date(2025, 6, 25)).stale
    assert evaluate_series_status("IBOV", ibov, date(2025, 6, 30)).stale
