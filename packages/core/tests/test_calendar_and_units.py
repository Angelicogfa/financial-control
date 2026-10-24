"""Unit tests for the national business-day calendar and explicit series unit conversion."""

from __future__ import annotations

from datetime import date

import pytest
from fincontrol_core.calendar import (
    add_business_days,
    business_days_between,
    count_business_days,
    easter_sunday,
    is_business_day,
    national_holidays,
    previous_business_day,
)
from fincontrol_core.domain.entities import MarketSeriesPoint
from fincontrol_core.domain.enums import SeriesUnit
from fincontrol_core.errors import ValidationError
from fincontrol_core.market.units import daily_rates, monthly_rates, rate_fraction


@pytest.mark.parametrize(
    ("year", "expected"),
    [(2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2026, date(2026, 4, 5))],
)
def test_easter_sunday(year: int, expected: date) -> None:
    assert easter_sunday(year) == expected


def test_national_holidays_2025_include_movable_dates() -> None:
    holidays = national_holidays(2025)
    for day in (
        date(2025, 3, 3),  # Carnival Monday
        date(2025, 3, 4),  # Carnival Tuesday
        date(2025, 4, 18),  # Good Friday
        date(2025, 6, 19),  # Corpus Christi
        date(2025, 11, 20),  # Black Consciousness Day
    ):
        assert day in holidays
    assert len(holidays) == 13


def test_black_consciousness_day_is_national_only_from_2024() -> None:
    assert date(2023, 11, 20) not in national_holidays(2023)
    assert date(2024, 11, 20) in national_holidays(2024)


def test_business_day_helpers() -> None:
    assert not is_business_day(date(2025, 6, 19))
    assert not is_business_day(date(2025, 6, 21))  # Saturday
    assert is_business_day(date(2025, 6, 20))
    # (Jun 2, Jun 30] in 2025: 20 weekdays minus Corpus Christi.
    assert count_business_days(date(2025, 6, 2), date(2025, 6, 30)) == 19
    assert business_days_between(date(2025, 6, 18), date(2025, 6, 20)) == [date(2025, 6, 20)]
    assert count_business_days(date(2025, 6, 30), date(2025, 6, 2)) == 0
    assert previous_business_day(date(2025, 6, 23)) == date(2025, 6, 20)
    assert add_business_days(date(2025, 6, 18), 1) == date(2025, 6, 20)


def _point(value: float, unit: SeriesUnit | None, on: date = date(2025, 1, 2)) -> MarketSeriesPoint:
    return MarketSeriesPoint("CDI", on, value, unit=unit)


def test_rate_fraction_requires_percentage_unit() -> None:
    assert rate_fraction(0.0393, SeriesUnit.PERCENT_PER_DAY) == pytest.approx(0.000393)
    with pytest.raises(ValidationError):
        rate_fraction(120_000.0, SeriesUnit.INDEX_POINTS)
    with pytest.raises(ValidationError):
        rate_fraction(0.04, None)


def test_daily_rates_convert_every_value_regardless_of_magnitude() -> None:
    rates = daily_rates(
        [
            _point(0.0393, SeriesUnit.PERCENT_PER_DAY, date(2024, 3, 1)),
            _point(0.0551, SeriesUnit.PERCENT_PER_DAY, date(2025, 3, 3)),
        ]
    )
    assert rates == {
        date(2024, 3, 1): pytest.approx(0.000393),
        date(2025, 3, 3): pytest.approx(0.000551),
    }


def test_monthly_rates_key_by_year_and_month() -> None:
    rates = monthly_rates([_point(1.31, SeriesUnit.PERCENT_PER_MONTH, date(2025, 2, 1))])
    assert rates == {(2025, 2): pytest.approx(0.0131)}


def test_series_with_wrong_unit_is_rejected() -> None:
    with pytest.raises(ValidationError, match="expected PERCENT_PER_DAY"):
        daily_rates([_point(0.16, SeriesUnit.PERCENT_PER_MONTH)])
