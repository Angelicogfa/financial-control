"""Freshness and gap diagnostics for persisted market/macro series (finding I-03)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from core.helpers.calendar import business_days_between, previous_business_day
from domain.shared.entities import MarketSeriesPoint
from domain.shared.enums import SeriesUnit

INDEX_STALE_AFTER_DAYS = 5
TRACKED_SERIES = ("CDI", "SELIC", "IPCA", "IBOV", "IFIX", "SP500")
MONTHLY_STALE_AFTER_MONTHS = 2


@dataclass(frozen=True)
class SeriesStatus:
    symbol: str
    unit: SeriesUnit | None
    points: int
    first_date: date | None
    last_date: date | None
    stale: bool
    missing_business_days: int


def _months_between(earlier: date, later: date) -> int:
    return (later.year - earlier.year) * 12 + later.month - earlier.month


def evaluate_series_status(
    symbol: str, points: Sequence[MarketSeriesPoint], today: date
) -> SeriesStatus:
    """Diagnose a series: stale when the last point is older than its publication lag.

    - Daily BCB rates (CDI, SELIC) are published on the next business day; gaps are the
      national business days inside the stored range that have no point.
    - Monthly IPCA is stale when more than two months behind.
    - Index levels are stale after five calendar days without a close.
    """
    if not points:
        return SeriesStatus(symbol, None, 0, None, None, True, 0)
    ordered = sorted(points, key=lambda p: p.reference_date)
    unit = ordered[-1].unit
    first, last = ordered[0].reference_date, ordered[-1].reference_date
    missing = 0

    if unit == SeriesUnit.PERCENT_PER_DAY:
        expected_last = previous_business_day(previous_business_day(today))
        stale = last < expected_last
        stored = {p.reference_date for p in ordered}
        missing = sum(
            1 for d in business_days_between(first - timedelta(days=1), last) if d not in stored
        )
    elif unit == SeriesUnit.PERCENT_PER_MONTH:
        stale = _months_between(last, today) > MONTHLY_STALE_AFTER_MONTHS
    else:
        stale = (today - last).days > INDEX_STALE_AFTER_DAYS

    return SeriesStatus(symbol, unit, len(ordered), first, last, stale, missing)
