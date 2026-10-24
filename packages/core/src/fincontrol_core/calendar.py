"""Brazilian national business-day calendar (ANBIMA convention) used by curves and snapshots.

Holidays: New Year, Carnival Monday and Tuesday, Good Friday, Tiradentes, Labour Day,
Corpus Christi, Independence Day, Our Lady Aparecida, All Souls, Republic Day,
Black Consciousness Day (national since 2024) and Christmas.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

BLACK_CONSCIOUSNESS_FIRST_YEAR = 2024


def easter_sunday(year: int) -> date:
    """Gregorian Easter Sunday (anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    leap = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * leap) // 451
    month, day = divmod(h + leap - 7 * m + 114, 31)
    return date(year, month, day + 1)


@lru_cache(maxsize=256)
def national_holidays(year: int) -> frozenset[date]:
    """National bank holidays for a given year."""
    easter = easter_sunday(year)
    holidays = {
        date(year, 1, 1),
        easter - timedelta(days=48),
        easter - timedelta(days=47),
        easter - timedelta(days=2),
        date(year, 4, 21),
        date(year, 5, 1),
        easter + timedelta(days=60),
        date(year, 9, 7),
        date(year, 10, 12),
        date(year, 11, 2),
        date(year, 11, 15),
        date(year, 12, 25),
    }
    if year >= BLACK_CONSCIOUSNESS_FIRST_YEAR:
        holidays.add(date(year, 11, 20))
    return frozenset(holidays)


def is_business_day(day: date) -> bool:
    return day.weekday() < 5 and day not in national_holidays(day.year)


def business_days_between(start: date, end: date) -> list[date]:
    """Business days in the half-open interval (start, end]."""
    days: list[date] = []
    current = start + timedelta(days=1)
    while current <= end:
        if is_business_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def count_business_days(start: date, end: date) -> int:
    """Number of business days in (start, end]."""
    return len(business_days_between(start, end))


def previous_business_day(day: date) -> date:
    """Last business day strictly before `day`."""
    current = day - timedelta(days=1)
    while not is_business_day(current):
        current -= timedelta(days=1)
    return current


def add_business_days(start: date, count: int) -> date:
    """Date reached after moving `count` business days forward from `start`."""
    current = start
    remaining = count
    while remaining > 0:
        current += timedelta(days=1)
        if is_business_day(current):
            remaining -= 1
    return current
