"""Explicit unit conversion of stored series into canonical domain fractions (ADR 0006).

Every series point carries the unit it was stored in. Rates are converted to fractions
exactly once, here; no code may infer a scale from the magnitude of a value.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from core.errors import ValidationError
from domain.shared.entities import MarketSeriesPoint
from domain.shared.enums import SeriesUnit

PERCENT_UNITS = frozenset({SeriesUnit.PERCENT_PER_DAY, SeriesUnit.PERCENT_PER_MONTH})

# Unit of each BCB SGS series code (CDI 12, SELIC 11, IPCA 433).
BCB_SERIES_UNITS: dict[str, SeriesUnit] = {
    "CDI": SeriesUnit.PERCENT_PER_DAY,
    "SELIC": SeriesUnit.PERCENT_PER_DAY,
    "IPCA": SeriesUnit.PERCENT_PER_MONTH,
}


def rate_fraction(value: float, unit: SeriesUnit | None) -> float:
    """Convert a percentage rate in a known unit into a fraction of the same period."""
    if unit not in PERCENT_UNITS:
        raise ValidationError(f"Series unit {unit!r} is not a percentage rate")
    return value / 100.0


def _require_unit(points: Iterable[MarketSeriesPoint], unit: SeriesUnit) -> list:
    materialized = list(points)
    for point in materialized:
        if point.unit != unit:
            raise ValidationError(
                f"Series {point.symbol} on {point.reference_date} has unit {point.unit!r}, "
                f"expected {unit.value}"
            )
    return materialized


def daily_rates(points: Iterable[MarketSeriesPoint]) -> dict[date, float]:
    """Map business day -> daily rate fraction for a PERCENT_PER_DAY series (CDI, SELIC)."""
    checked = _require_unit(points, SeriesUnit.PERCENT_PER_DAY)
    return {p.reference_date: rate_fraction(p.value, p.unit) for p in checked}


def monthly_rates(points: Iterable[MarketSeriesPoint]) -> dict[tuple[int, int], float]:
    """Map (year, month) -> monthly rate fraction for a PERCENT_PER_MONTH series (IPCA)."""
    checked = _require_unit(points, SeriesUnit.PERCENT_PER_MONTH)
    return {
        (p.reference_date.year, p.reference_date.month): rate_fraction(p.value, p.unit)
        for p in checked
    }
