"""Point-in-time market history for simulations (design 3.2, risk R1).

`MarketHistory` holds total-return price series (already in BRL) and monthly IPCA. A
`PointInTimeView` only answers with data dated on or before its date: asking for the future
raises `LookAheadError`, so the engine cannot use what was not known at each step.
"""

from __future__ import annotations

import bisect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from core.helpers.calendar import is_business_day


class LookAheadError(RuntimeError):
    """A simulation step asked for data dated after the simulated day."""


@dataclass(frozen=True)
class PriceSeries:
    """Dated prices of one instrument, sorted, without duplicates."""

    dates: tuple[date, ...]
    prices: tuple[float, ...]

    @classmethod
    def from_points(cls, points: Sequence[tuple[date, float]]) -> PriceSeries:
        clean = sorted({d: p for d, p in points if p is not None and p > 0}.items())
        return cls(tuple(d for d, _ in clean), tuple(p for _, p in clean))

    @property
    def first_date(self) -> date | None:
        return self.dates[0] if self.dates else None

    def last_on_or_before(self, day: date) -> float | None:
        index = bisect.bisect_right(self.dates, day) - 1
        return self.prices[index] if index >= 0 else None


@dataclass(frozen=True)
class MarketHistory:
    """Every series a simulation may read, keyed by symbol."""

    series: Mapping[str, PriceSeries]
    # (year, month) -> monthly IPCA as a fraction, for contributions corrected by inflation.
    ipca_monthly: Mapping[tuple[int, int], float] = field(default_factory=dict)

    def view(self, as_of: date) -> PointInTimeView:
        return PointInTimeView(self, as_of)


@dataclass(frozen=True)
class PointInTimeView:
    history: MarketHistory
    as_of: date

    def price(self, symbol: str, day: date | None = None) -> float | None:
        """Last price on or before `day` (default: the view date); never a later one."""
        target = day or self.as_of
        if target > self.as_of:
            raise LookAheadError(f"{symbol} asked for {target} while simulating {self.as_of}")
        series = self.history.series.get(symbol)
        return series.last_on_or_before(target) if series else None

    def available(self, symbol: str) -> bool:
        series = self.history.series.get(symbol)
        return bool(series and series.first_date and series.first_date <= self.as_of)

    def ipca(self, year: int, month: int) -> float | None:
        if (year, month) > (self.as_of.year, self.as_of.month):
            raise LookAheadError(f"IPCA {month}/{year} asked while simulating {self.as_of}")
        return self.history.ipca_monthly.get((year, month))


def month_ends(start: date, end: date) -> list[date]:
    """Last business day of every month between `start` and `end` (inclusive)."""
    out: list[date] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
        last = date(next_year, next_month, 1) - timedelta(days=1)
        while not is_business_day(last):
            last -= timedelta(days=1)
        if start <= last <= end:
            out.append(last)
        year, month = next_year, next_month
    return out


def accumulate_rate_index(
    daily_percent: Sequence[tuple[date, float]], *, base: float = 1.0
) -> PriceSeries:
    """Price-like index of a daily rate series (CDI in % a day): base x prod(1 + r)."""
    level = base
    points: list[tuple[date, float]] = []
    for day, rate in sorted(daily_percent):
        level *= 1.0 + rate / 100.0
        points.append((day, level))
    return PriceSeries.from_points(points)
