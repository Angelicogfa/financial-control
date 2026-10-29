"""Price history by period for the asset chart: 6 months, 1, 2 and 5 years, or everything.

The provider returns daily closes; a 20-year series has about 5,000 of them, more than a chart
can draw or a reader can tell apart. The series is cleaned of isolated bad prints (the same
rule as the health checks) and thinned to at most `MAX_CHART_POINTS`, always keeping the first
and the last close so the period change is exact. The summary (change, high, low) is computed
on the cleaned daily series, before thinning.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from domain.market.entities import PricePoint
from domain.market.services.price_sanity import price_spikes

# Provider period codes (brapi and Yahoo use the same ones).
PRICE_RANGES = ("6mo", "1y", "2y", "5y", "max")
MAX_CHART_POINTS = 500


@dataclass(frozen=True)
class PriceChart:
    range_period: str
    points: list[tuple[date, float]]
    change: float | None  # last close over the first, minus 1
    high: tuple[date, float] | None
    low: tuple[date, float] | None
    dropped_spikes: int  # bad-print runs removed


def thin(points: Sequence[tuple[date, float]], max_points: int) -> list[tuple[date, float]]:
    """At most `max_points` evenly spaced points, first and last always kept."""
    n = len(points)
    if n <= max_points or max_points < 2:
        return list(points)
    step = (n - 1) / (max_points - 1)
    return [points[round(i * step)] for i in range(max_points)]


def price_chart(
    range_period: str, history: Sequence[PricePoint], max_points: int = MAX_CHART_POINTS
) -> PriceChart:
    ordered = sorted((p for p in history if p.close and p.close > 0), key=lambda p: p.date)
    keep, spikes = price_spikes([p.date for p in ordered], [p.close for p in ordered])
    clean = [(p.date, float(p.close)) for p, ok in zip(ordered, keep, strict=True) if ok]
    if not clean:
        return PriceChart(range_period, [], None, None, None, len(spikes))
    return PriceChart(
        range_period=range_period,
        points=thin(clean, max_points),
        change=clean[-1][1] / clean[0][1] - 1.0 if len(clean) >= 2 else None,
        high=max(clean, key=lambda p: p[1]),
        low=min(clean, key=lambda p: p[1]),
        dropped_spikes=len(spikes),
    )
