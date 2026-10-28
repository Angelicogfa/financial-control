"""Complementary risk and performance statistics for the portfolio health diagnosis (29.3, 29.6).

Pure functions over periodic simple returns: drawdown state, Ulcer Index, tracking error,
Information Ratio, Omega, rolling 12-month windows, monthly consistency against the CDI,
historical stress with the current weights and bootstrap confidence intervals.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from domain.portfolio.services.analytics import (
    TRADING_DAYS_PER_YEAR,
    cagr,
    cumulative_return,
    drawdown_series,
    sharpe_ratio,
)
from domain.shared.entities import PortfolioSnapshotEntity

ROLLING_WINDOW = 252
STRESS_WINDOW = 21
BOOTSTRAP_SAMPLES = 1000
BOOTSTRAP_SEED = 20261027


@dataclass(frozen=True)
class DrawdownState:
    """Current distance from the running peak and how long it has lasted."""

    current: float
    periods: int
    peak_date: date | None = None


@dataclass(frozen=True)
class RollingPoint:
    """Statistics of the trailing window that closes on `end`."""

    end: date
    cumulative_return: float
    sharpe: float


@dataclass(frozen=True)
class ConfidenceInterval:
    low: float
    high: float
    confidence: float = 0.95


@dataclass(frozen=True)
class StressResult:
    """Worst historical window and drawdown of the current weights replayed on past returns."""

    worst_window_return: float
    window_start: date | None
    window_end: date | None
    max_drawdown: float
    observations: int


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _sample_std(values: Sequence[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mu = _mean(values)
    return math.sqrt(sum((x - mu) ** 2 for x in values) / (n - 1))


def drawdown_state(dates: Sequence[date], returns: Sequence[float]) -> DrawdownState:
    """Current drawdown (<= 0) and the number of periods since the last peak."""
    if not returns:
        return DrawdownState(current=0.0, periods=0)
    wealth = 1.0
    peak = 1.0
    peak_index = -1
    for i, r in enumerate(returns):
        wealth *= 1.0 + r
        if wealth >= peak:
            peak = wealth
            peak_index = i
    current = (wealth - peak) / peak if peak > 0 else 0.0
    periods = len(returns) - 1 - peak_index
    peak_date = dates[peak_index] if 0 <= peak_index < len(dates) else None
    return DrawdownState(current=current, periods=periods, peak_date=peak_date)


def ulcer_index(returns: Sequence[float]) -> float:
    """Root mean square of the drawdowns: depth and duration of losses in one number."""
    dd = drawdown_series(returns)
    if not dd:
        return 0.0
    return math.sqrt(sum(d * d for d in dd) / len(dd))


def _active(
    returns: Sequence[float], benchmark: Sequence[float | None]
) -> tuple[list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    for r, b in zip(returns, benchmark, strict=False):
        if b is not None:
            xs.append(r)
            ys.append(b)
    return xs, ys


def tracking_error(
    returns: Sequence[float],
    benchmark: Sequence[float | None],
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
) -> float | None:
    """Annualized standard deviation of the active return (portfolio - benchmark)."""
    xs, ys = _active(returns, benchmark)
    if len(xs) < 2:
        return None
    active = [x - y for x, y in zip(xs, ys, strict=True)]
    return _sample_std(active) * math.sqrt(periods_per_year)


def information_ratio(
    returns: Sequence[float],
    benchmark: Sequence[float | None],
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
) -> float | None:
    """Annualized mean active return divided by the tracking error."""
    xs, ys = _active(returns, benchmark)
    te = tracking_error(xs, ys, periods_per_year)
    if te is None or te <= 1e-12:
        return None
    active_mean = _mean([x - y for x, y in zip(xs, ys, strict=True)]) * periods_per_year
    return active_mean / te


def omega_ratio(
    returns: Sequence[float], thresholds: Sequence[float | None] | float = 0.0
) -> float | None:
    """Probability-weighted gains over losses relative to a threshold (e.g. the daily CDI)."""
    if not returns:
        return None
    if isinstance(thresholds, int | float):
        levels: Sequence[float | None] = [float(thresholds)] * len(returns)
    else:
        levels = thresholds
    gains = 0.0
    losses = 0.0
    for r, t in zip(returns, levels, strict=False):
        if t is None:
            continue
        diff = r - t
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    if losses <= 1e-12:
        return None
    return gains / losses


def rolling_windows(
    dates: Sequence[date],
    returns: Sequence[float],
    *,
    window: int = ROLLING_WINDOW,
    annual_risk_free_rate: float = 0.1075,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
    step: int = 21,
) -> list[RollingPoint]:
    """Trailing-window return and Sharpe, sampled every `step` periods (always the last)."""
    n = len(returns)
    if n < window:
        return []
    ends = list(range(window - 1, n, step))
    if ends[-1] != n - 1:
        ends.append(n - 1)
    points: list[RollingPoint] = []
    for end in ends:
        chunk = returns[end - window + 1 : end + 1]
        points.append(
            RollingPoint(
                end=dates[end],
                cumulative_return=round(cumulative_return(chunk), 4),
                sharpe=round(sharpe_ratio(chunk, annual_risk_free_rate, periods_per_year), 4),
            )
        )
    return points


def monthly_returns(dates: Sequence[date], returns: Sequence[float]) -> dict[str, float]:
    """Compound periodic returns into calendar months keyed 'YYYY-MM'."""
    factors: dict[str, float] = {}
    for d, r in zip(dates, returns, strict=False):
        key = f"{d.year:04d}-{d.month:02d}"
        factors[key] = factors.get(key, 1.0) * (1.0 + r)
    return {k: v - 1.0 for k, v in sorted(factors.items())}


def consistency_against(
    dates: Sequence[date],
    returns: Sequence[float],
    benchmark: Sequence[float | None],
) -> tuple[float | None, int]:
    """Share of months the portfolio beat the benchmark, and the number of months compared."""
    xs_dates: list[date] = []
    xs: list[float] = []
    ys: list[float] = []
    for d, r, b in zip(dates, returns, benchmark, strict=False):
        if b is not None:
            xs_dates.append(d)
            xs.append(r)
            ys.append(b)
    mine = monthly_returns(xs_dates, xs)
    theirs = monthly_returns(xs_dates, ys)
    months = [m for m in mine if m in theirs]
    if not months:
        return None, 0
    beaten = sum(1 for m in months if mine[m] > theirs[m])
    return beaten / len(months), len(months)


def weighted_returns(
    weights: Mapping[str, float], series: Mapping[str, Sequence[float | None]]
) -> list[float]:
    """Hypothetical returns of fixed `weights` replayed over aligned asset returns.

    Gaps (None) count as a flat period for that asset.
    """
    names = [n for n in weights if n in series]
    if not names:
        return []
    length = min(len(series[n]) for n in names)
    out: list[float] = []
    for t in range(length):
        out.append(sum(weights[n] * (series[n][t] or 0.0) for n in names))
    return out


def historical_stress(
    dates: Sequence[date], returns: Sequence[float], *, window: int = STRESS_WINDOW
) -> StressResult | None:
    """Worst compounded `window`-period return and the deepest drawdown of `returns`."""
    n = len(returns)
    if n < window:
        return None
    worst = math.inf
    worst_end = window - 1
    log_sum = 0.0
    logs = [math.log1p(max(r, -0.999999)) for r in returns]
    for i in range(n):
        log_sum += logs[i]
        if i >= window:
            log_sum -= logs[i - window]
        if i >= window - 1 and log_sum < worst:
            worst = log_sum
            worst_end = i
    dd = drawdown_series(returns)
    return StressResult(
        worst_window_return=round(math.expm1(worst), 4),
        window_start=dates[worst_end - window + 1] if dates else None,
        window_end=dates[worst_end] if dates else None,
        max_drawdown=round(min(dd), 4) if dd else 0.0,
        observations=n,
    )


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    idx = q * (len(sorted_values) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    frac = idx - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def bootstrap_intervals(
    returns: Sequence[float],
    *,
    annual_risk_free_rate: float = 0.1075,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
    samples: int = BOOTSTRAP_SAMPLES,
    confidence: float = 0.95,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[ConfidenceInterval, ConfidenceInterval] | None:
    """Percentile bootstrap intervals for the annualized Sharpe and the CAGR.

    Resamples the periodic returns with replacement (i.i.d.) using a fixed seed, so the
    same history always yields the same interval.
    """
    n = len(returns)
    if n < 2:
        return None
    rng = random.Random(seed)
    sharpes: list[float] = []
    growths: list[float] = []
    values = list(returns)
    for _ in range(samples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        sharpes.append(sharpe_ratio(sample, annual_risk_free_rate, periods_per_year))
        growths.append(cagr(cumulative_return(sample), n, periods_per_year))
    sharpes.sort()
    growths.sort()
    tail = (1.0 - confidence) / 2.0
    return (
        ConfidenceInterval(
            low=round(_percentile(sharpes, tail), 4),
            high=round(_percentile(sharpes, 1.0 - tail), 4),
            confidence=confidence,
        ),
        ConfidenceInterval(
            low=round(_percentile(growths, tail), 4),
            high=round(_percentile(growths, 1.0 - tail), 4),
            confidence=confidence,
        ),
    )


def class_time_weighted_returns(
    snapshots: Sequence[PortfolioSnapshotEntity],
) -> dict[str, float]:
    """Approximate cumulative TWR of each ARCA class from the per-class snapshot values.

    The class flow of a period is the change in its invested cost, so a sale adds its
    realized gain to the return of that period and class earnings are left out (TD-07).
    """
    ordered = sorted(snapshots, key=lambda s: s.snapshot_date)
    factors: dict[str, float] = {}
    for prev, curr in zip(ordered[:-1], ordered[1:], strict=False):
        for name, data in curr.by_class.items():
            before = prev.by_class.get(name)
            if not before:
                continue
            start = float(before.get("current_value") or 0.0)
            if start <= 0:
                continue
            flow = float(data.get("invested_value") or 0.0) - float(
                before.get("invested_value") or 0.0
            )
            # Purchases count from the start of the period, as in the portfolio TWR.
            r = (float(data.get("current_value") or 0.0) - start - flow) / (start + max(flow, 0.0))
            factors[name] = factors.get(name, 1.0) * (1.0 + r)
    return {name: round(f - 1.0, 4) for name, f in factors.items()}


def days_out_of_band(
    snapshots: Sequence[PortfolioSnapshotEntity],
    bands: Mapping[str, float],
    as_of: date,
) -> dict[str, int]:
    """Days each class has been outside its band without interruption up to the last snapshot.

    `bands` maps the class name to the tolerance in percentage points; the target of each
    snapshot is the one stored with it.
    """
    ordered = sorted(snapshots, key=lambda s: s.snapshot_date, reverse=True)
    out: dict[str, int] = {}
    for name, band in bands.items():
        since: date | None = None
        for snap in ordered:
            data = snap.by_class.get(name)
            if not data:
                break
            deviation = float(data.get("current_pct") or 0.0) - float(data.get("target_pct") or 0.0)
            if abs(deviation) <= band:
                break
            since = snap.snapshot_date
        if since is not None:
            out[name] = (as_of - since).days
    return out
