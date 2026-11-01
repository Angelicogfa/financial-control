"""Measures of the live scoreboard (design 36, section 6), on the same flow for everyone.

The fair comparison is the money-weighted return (IRR) on the same contributions; the TWR,
the volatility and the deepest drawdown come from the monthly returns. The real portfolio's
place among the random portfolios is the share of them it beats, with the credible interval.
The verdict "better or worse than your portfolio" waits for 12 months of prospective record
(decision 10.1.12); the measures are shown from the first day.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from domain.comparison.points import Point
from domain.portfolio.services.analytics import annualized_volatility, max_drawdown
from domain.simulation.bayes import credible_interval
from domain.simulation.engine import money_weighted_return

MONTHS_PER_YEAR = 12.0
MIN_VERDICT_MONTHS = 12


@dataclass(frozen=True)
class Summary:
    start: date
    end: date
    final_value: float
    contributed: float
    gain: float
    irr: float | None  # annual money-weighted return of the flow
    twr: float  # cumulative time-weighted return
    annual_twr: float
    volatility: float
    max_drawdown: float
    fees: float
    taxes: float

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["start"] = self.start.isoformat()
        data["end"] = self.end.isoformat()
        return data


def since(points: Sequence[Point], start: date | None) -> list[Point]:
    """The points from `start` on, opened by the last point before it as money in."""
    if start is None:
        return list(points)
    before = [p for p in points if p.day < start]
    after = [p for p in points if p.day >= start]
    if not after or not before:
        return after
    last = before[-1]
    opening = Point(
        day=last.day,
        flow=last.value,
        contributed=last.value,
        value=last.value,
        cash=last.cash,
        fees=last.fees,
        taxes=last.taxes,
    )
    return [opening, *after]


def monthly_returns(points: Sequence[Point]) -> list[float]:
    """Time-weighted return of each month (flows at the end of their day)."""
    months: dict[tuple[int, int], float] = {}
    for prev, curr in zip(points, points[1:], strict=False):
        if prev.value <= 0:
            continue
        r = (curr.value - curr.flow - prev.value) / prev.value
        key = (curr.day.year, curr.day.month)
        months[key] = (1.0 + months.get(key, 0.0)) * (1.0 + r) - 1.0
    return [months[k] for k in sorted(months)]


def summarize(points: Sequence[Point], start: date | None = None) -> Summary | None:
    part = since(points, start)
    if not part:
        return None
    last = part[-1]
    returns = monthly_returns(part)
    growth = 1.0
    for r in returns:
        growth *= 1.0 + r
    years = max((last.day - part[0].day).days / 365.0, 1.0 / 365.0)
    first = part[0]
    return Summary(
        start=first.day,
        end=last.day,
        final_value=last.value,
        contributed=round(sum(p.flow for p in part), 2),
        gain=round(last.value - sum(p.flow for p in part), 2),
        irr=money_weighted_return([(p.day, p.flow) for p in part], (last.day, last.value)),
        twr=round(growth - 1.0, 6),
        annual_twr=round(growth ** (1.0 / years) - 1.0, 6) if growth > 0 else -1.0,
        volatility=round(annualized_volatility(returns, MONTHS_PER_YEAR), 6),
        max_drawdown=round(max_drawdown(returns), 6),
        fees=round(last.fees - (first.fees if start else 0.0), 2),
        taxes=round(last.taxes - (first.taxes if start else 0.0), 2),
    )


@dataclass(frozen=True)
class Rank:
    """Where the real portfolio stands among the random ones, by the IRR on the same flow."""

    portfolios: int
    beaten: int
    share: float
    low: float
    high: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def rank_among(yours: float | None, randoms: Sequence[float | None]) -> Rank | None:
    values = [r for r in randoms if r is not None]
    if yours is None or not values:
        return None
    beaten = sum(1 for r in values if yours > r)
    low, high = credible_interval(beaten, len(values))
    return Rank(
        portfolios=len(values),
        beaten=beaten,
        share=round(beaten / len(values), 4),
        low=low,
        high=high,
    )


def months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def verdict_ready(prospective_start: date, today: date) -> bool:
    return months_between(prospective_start, today) >= MIN_VERDICT_MONTHS
