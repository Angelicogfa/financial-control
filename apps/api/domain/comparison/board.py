"""The live scoreboard as read by the screen (Phase 45.8a): one line per strategy.

Every strategy is compared with your portfolio over the same period and the same flow (the
recommendation starts later, at its first run, with your patrimony of that day). The random
portfolios become a distribution: your place among them and their 5%-95% band on the curve.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from domain.comparison.metrics import (
    Rank,
    Summary,
    months_between,
    rank_among,
    summarize,
    verdict_ready,
)
from domain.comparison.points import Point
from domain.comparison.repositories import ComparisonPortfolio
from domain.comparison.strategies import RANDOM, YOURS


@dataclass(frozen=True)
class StrategyLine:
    key: str
    label: str
    started: date
    retroactive: bool  # part of the record was rebuilt from the past
    whole: Summary
    yours: Summary  # your portfolio over the same period
    difference: float  # final value of the strategy minus yours, same money and dates
    prospective: Summary | None = None
    yours_prospective: Summary | None = None


@dataclass(frozen=True)
class RandomLine:
    portfolios: int
    rank: Rank | None  # where your portfolio stands, whole period
    rank_prospective: Rank | None
    irr_low: float | None
    irr_mid: float | None
    irr_high: float | None


@dataclass(frozen=True)
class CurvePoint:
    day: date
    yours: float
    values: dict[str, float] = field(default_factory=dict)
    random_low: float | None = None
    random_high: float | None = None


@dataclass(frozen=True)
class Board:
    as_of: date
    prospective_since: date
    prospective_months: int
    verdict_ready: bool
    yours: Summary
    lines: list[StrategyLine]
    randoms: RandomLine | None
    curve: list[CurvePoint]


def _percentiles(values: Sequence[float]) -> tuple[float | None, float | None, float | None]:
    if not values:
        return None, None, None
    low, mid, high = np.percentile(np.asarray(values, dtype=float), [5, 50, 95])
    return round(float(low), 6), round(float(mid), 6), round(float(high), 6)


def _value_on(points: Sequence[Point], day: date) -> float | None:
    for p in points:
        if p.day == day:
            return p.value
    return None


def _curve(
    yours: ComparisonPortfolio,
    others: Sequence[ComparisonPortfolio],
    randoms: Sequence[ComparisonPortfolio],
) -> list[CurvePoint]:
    days = [p.day for p in yours.points]
    month_last = {}
    for d in days:
        month_last[(d.year, d.month)] = d
    out = []
    by_day = [{p.day: p.value for p in r.points} for r in randoms]
    for day in sorted(month_last.values()):
        values = {}
        for row in others:
            value = _value_on(row.points, day)
            if value is not None:
                values[row.key] = value
        sample = [m[day] for m in by_day if day in m]
        low, _, high = _percentiles(sample)
        out.append(
            CurvePoint(
                day=day,
                yours=_value_on(yours.points, day) or 0.0,
                values=values,
                random_low=round(low, 2) if low is not None else None,
                random_high=round(high, 2) if high is not None else None,
            )
        )
    return out


def build_board(rows: Sequence[ComparisonPortfolio], today: date) -> Board | None:
    """The scoreboard of the stored portfolios (None while your portfolio has no record)."""
    yours = next((r for r in rows if r.key == YOURS), None)
    if yours is None or not yours.points:
        return None
    whole_yours = summarize(yours.points)
    if whole_yours is None:
        return None
    since = min((r.created_on for r in rows if r.key != YOURS), default=yours.created_on)
    lines = []
    others = [r for r in rows if r.key not in (YOURS, RANDOM) and r.points]
    for row in others:
        started = row.points[0].day
        late_start = started > yours.points[0].day
        whole = summarize(row.points)
        mine = summarize(yours.points, started if late_start else None)
        if whole is None or mine is None:
            continue
        lines.append(
            StrategyLine(
                key=row.key,
                label=row.label,
                started=started,
                retroactive=started < row.created_on,
                whole=whole,
                yours=mine,
                difference=round(whole.final_value - mine.final_value, 2),
                prospective=summarize(row.points, row.created_on),
                yours_prospective=summarize(yours.points, max(row.created_on, started)),
            )
        )
    randoms = [r for r in rows if r.key == RANDOM and r.points]
    random_line = None
    if randoms:
        irrs = [s.irr for s in (summarize(r.points) for r in randoms) if s is not None]
        later = [summarize(r.points, r.created_on) for r in randoms]
        mine_later = summarize(yours.points, since)
        low, mid, high = _percentiles([i for i in irrs if i is not None])
        random_line = RandomLine(
            portfolios=len(randoms),
            rank=rank_among(whole_yours.irr, irrs),
            rank_prospective=(
                rank_among(mine_later.irr, [s.irr for s in later if s is not None])
                if mine_later is not None
                else None
            ),
            irr_low=low,
            irr_mid=mid,
            irr_high=high,
        )
    return Board(
        as_of=today,
        prospective_since=since,
        prospective_months=max(months_between(since, today), 0),
        verdict_ready=verdict_ready(since, today),
        yours=whole_yours,
        lines=lines,
        randoms=random_line,
        curve=_curve(yours, others, randoms),
    )
