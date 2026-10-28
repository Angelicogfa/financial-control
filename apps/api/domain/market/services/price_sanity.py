"""Isolated bad prints in price histories (Phase 32.4).

Free providers sometimes return a few days at a wildly wrong scale and then come back: Yahoo
had XPML11 at R$ 1.07 from 14 to 16/01/2026 between closes near R$ 110, a -99% day followed
by +10,000%. One such run is enough to make a volatility of hundreds of percent a year and to
give a 0.8% position 100% of the portfolio risk.

A run is dropped when it starts more than `SPIKE_FACTOR` away from the last good price, lasts
at most `MAX_SPIKE_POINTS` points and the series then returns close to where it was. A level
that does not come back (an unapplied split, a real crash) is kept: it is not a bad print.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

SPIKE_FACTOR = 3.0
MAX_SPIKE_POINTS = 5
# How close to the last good price the series must come back for the run to be a bad print.
RETURN_TOLERANCE = 1.5


@dataclass(frozen=True)
class PriceSpike:
    first_date: date
    last_date: date
    points: int
    price: float  # the first wrong price
    reference: float  # the last good price before it

    def describe(self) -> str:
        period = (
            f"{self.first_date:%d/%m/%Y}"
            if self.first_date == self.last_date
            else f"{self.first_date:%d/%m/%Y} a {self.last_date:%d/%m/%Y}"
        )
        return f"{period} ({self.price:.2f} contra {self.reference:.2f})"


def _within(value: float, reference: float, factor: float) -> bool:
    return reference / factor <= value <= reference * factor


def price_spikes(
    dates: Sequence[date], prices: Sequence[float]
) -> tuple[list[bool], list[PriceSpike]]:
    """Which points to keep, and the bad-print runs found (dates and prices sorted by date)."""
    n = len(prices)
    keep = [True] * n
    spikes: list[PriceSpike] = []
    last_good: float | None = None
    i = 0
    while i < n:
        price = prices[i]
        if last_good is not None and price > 0 and not _within(price, last_good, SPIKE_FACTOR):
            j = i
            while (
                j < n
                and j - i < MAX_SPIKE_POINTS
                and not _within(prices[j], last_good, SPIKE_FACTOR)
            ):
                j += 1
            if j < n and _within(prices[j], last_good, RETURN_TOLERANCE):
                for k in range(i, j):
                    keep[k] = False
                spikes.append(PriceSpike(dates[i], dates[j - 1], j - i, price, last_good))
                i = j
                continue
        if price > 0:
            last_good = price
        i += 1
    return keep, spikes
