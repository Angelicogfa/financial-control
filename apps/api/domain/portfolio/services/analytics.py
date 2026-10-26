"""Quantitative risk, return, and benchmark analytics engine.

Provides pure functions for Simple/Log Returns, Time-Weighted Return (TWR), CAGR,
Annualized Volatility, Sharpe, Sortino, Drawdown Series, Max Drawdown, Calmar,
Historical & Parametric VaR (95%), CVaR (95%), Beta, Jensen's Alpha, Correlation Matrix,
Real Return deflated by IPCA, and normalized Base-100 curves against IBOV, IFIX, S&P 500,
CDI, and IPCA.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from domain.shared.entities import PortfolioSnapshotEntity

TRADING_DAYS_PER_YEAR = 252.0
Z_SCORE_95 = 1.6448536269514722


@dataclass(frozen=True)
class BenchmarkComparison:
    """Comparison metrics against a specific benchmark (IBOV, IFIX, S&P 500, CDI, IPCA)."""

    benchmark: str
    benchmark_return: float
    excess_return: float
    beta: float | None = None
    alpha_annual: float | None = None
    correlation: float | None = None


@dataclass(frozen=True)
class RiskReturnSummary:
    """Comprehensive statistical and risk-return summary for a portfolio or asset."""

    observations: int
    cumulative_return: float
    cagr: float
    real_return_vs_ipca: float
    annualized_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    var_95_historical: float
    var_95_parametric: float
    cvar_95: float
    benchmarks: list[BenchmarkComparison] = field(default_factory=list)
    drawdown_curve: list[float] = field(default_factory=list)


def simple_returns(prices: Sequence[float]) -> list[float]:
    """Compute period-over-period simple returns: (P_t / P_{t-1}) - 1."""
    if len(prices) < 2:
        return []
    out: list[float] = []
    for prev, curr in zip(prices[:-1], prices[1:], strict=False):
        if prev > 0:
            out.append((curr / prev) - 1.0)
    return out


def log_returns(prices: Sequence[float]) -> list[float]:
    """Compute period-over-period logarithmic returns: ln(P_t / P_{t-1})."""
    if len(prices) < 2:
        return []
    out: list[float] = []
    for prev, curr in zip(prices[:-1], prices[1:], strict=False):
        if prev > 0 and curr > 0:
            out.append(math.log(curr / prev))
    return out


def cumulative_return(returns: Sequence[float]) -> float:
    """Chain periodic simple returns into cumulative return: prod(1 + r_t) - 1."""
    factor = 1.0
    for r in returns:
        factor *= 1.0 + r
    return factor - 1.0


def dated_time_weighted_returns(
    snapshots: Sequence[PortfolioSnapshotEntity],
) -> tuple[list[date], list[float]]:
    """Sub-period TWR returns, each dated by the snapshot that closes the period.

    r_t = (V_t - V_{t-1} - CF_t + D_t) / V_{t-1}, where CF_t is the net external flow
    (purchases minus sale proceeds) and D_t the earnings received in the period, taken
    from the change in cumulative earnings (finding I-09).
    """
    if len(snapshots) < 2:
        return [], []
    ordered = sorted(snapshots, key=lambda s: s.snapshot_date)
    dates: list[date] = []
    sub_returns: list[float] = []
    for prev, curr in zip(ordered[:-1], ordered[1:], strict=False):
        if prev.market_value > 0:
            income = curr.earnings_cum - prev.earnings_cum
            r_t = (
                curr.market_value - prev.market_value - curr.net_flow + income
            ) / prev.market_value
            dates.append(curr.snapshot_date)
            sub_returns.append(r_t)
    return dates, sub_returns


def time_weighted_return(snapshots: Sequence[PortfolioSnapshotEntity]) -> list[float]:
    """Compute sub-period returns isolating external cash flows and adding income (TWR)."""
    return dated_time_weighted_returns(snapshots)[1]


def dated_simple_returns(
    dates: Sequence[date], prices: Sequence[float]
) -> tuple[list[date], list[float]]:
    """Simple returns of a price series, each dated by the price that closes the period."""
    returns = simple_returns(prices)
    return list(dates[1 : len(returns) + 1]), returns


def align_to_base(
    base_dates: Sequence[date],
    other_dates: Sequence[date],
    other_returns: Sequence[float],
) -> list[float | None]:
    """Re-express `other` returns over the base periods by compounding (finding I-09).

    For base period i ending on base_dates[i], the aligned value compounds every `other`
    return dated in (base_dates[i-1], base_dates[i]] (for i = 0, only the return dated on
    base_dates[0]). Periods with no `other` observation are None.
    """
    pairs = sorted(zip(other_dates, other_returns, strict=False))
    aligned: list[float | None] = []
    cursor = 0
    previous: date | None = None
    for end in base_dates:
        factor = 1.0
        seen = False
        while cursor < len(pairs) and pairs[cursor][0] <= end:
            other_date, other_ret = pairs[cursor]
            if (previous is None and other_date == end) or (
                previous is not None and other_date > previous
            ):
                factor *= 1.0 + other_ret
                seen = True
            cursor += 1
        aligned.append(factor - 1.0 if seen else None)
        previous = end
    return aligned


def _paired(
    base: Sequence[float], aligned: Sequence[float | None]
) -> tuple[list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    for x, y in zip(base, aligned, strict=False):
        if y is not None:
            xs.append(x)
            ys.append(y)
    return xs, ys


def cagr(
    cumulative_ret: float,
    num_periods: int,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
) -> float:
    """Compound Annual Growth Rate from cumulative return and number of periods."""
    if num_periods <= 0 or cumulative_ret <= -1.0:
        return 0.0
    years = num_periods / periods_per_year
    if years <= 0:
        return 0.0
    return (1.0 + cumulative_ret) ** (1.0 / years) - 1.0


def real_return_vs_inflation(nominal_return: float, inflation_return: float) -> float:
    """Fisher equation for real return deflated by IPCA: (1 + R_nom) / (1 + IPCA) - 1."""
    if inflation_return <= -1.0:
        return nominal_return
    return ((1.0 + nominal_return) / (1.0 + inflation_return)) - 1.0


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _sample_std(values: Sequence[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mu = _mean(values)
    variance = sum((x - mu) ** 2 for x in values) / (n - 1)
    return math.sqrt(variance)


def annualized_volatility(
    returns: Sequence[float],
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualized standard deviation of periodic returns."""
    return _sample_std(returns) * math.sqrt(periods_per_year)


def sharpe_ratio(
    returns: Sequence[float],
    annual_risk_free_rate: float = 0.1075,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualized Sharpe Ratio against a risk-free rate (default CDI)."""
    if len(returns) < 2:
        return 0.0
    vol = annualized_volatility(returns, periods_per_year)
    if vol <= 1e-12:
        return 0.0
    rf_periodic = (1.0 + annual_risk_free_rate) ** (1.0 / periods_per_year) - 1.0
    excess_mean_annual = (_mean(returns) - rf_periodic) * periods_per_year
    return excess_mean_annual / vol


def sortino_ratio(
    returns: Sequence[float],
    annual_risk_free_rate: float = 0.1075,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualized Sortino Ratio penalizing only downside deviations below the risk-free rate."""
    n = len(returns)
    if n < 2:
        return 0.0
    rf_periodic = (1.0 + annual_risk_free_rate) ** (1.0 / periods_per_year) - 1.0
    downside_sq = [min(0.0, r - rf_periodic) ** 2 for r in returns]
    downside_dev = math.sqrt(sum(downside_sq) / n) * math.sqrt(periods_per_year)
    if downside_dev <= 1e-12:
        return 0.0
    excess_mean_annual = (_mean(returns) - rf_periodic) * periods_per_year
    return excess_mean_annual / downside_dev


def drawdown_series(returns: Sequence[float]) -> list[float]:
    """Compute underwater drawdown series (values <= 0.0) from periodic returns."""
    if not returns:
        return []
    wealth = 1.0
    peak = 1.0
    dd: list[float] = []
    for r in returns:
        wealth *= 1.0 + r
        if wealth > peak:
            peak = wealth
        dd.append((wealth - peak) / peak if peak > 0 else 0.0)
    return dd


def max_drawdown(returns: Sequence[float]) -> float:
    """Return the deepest drawdown (negative fraction, e.g., -0.15 for -15%)."""
    dd = drawdown_series(returns)
    return min(dd) if dd else 0.0


def calmar_ratio(
    returns: Sequence[float],
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
) -> float:
    """Calmar Ratio: CAGR / |Max Drawdown|."""
    mdd = abs(max_drawdown(returns))
    if mdd <= 1e-12:
        return 0.0
    cum = cumulative_return(returns)
    ann_cagr = cagr(cum, len(returns), periods_per_year)
    return ann_cagr / mdd


def historical_var(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Historical Value at Risk at `confidence` level (returned as positive loss fraction)."""
    if not returns:
        return 0.0
    ordered = sorted(returns)
    alpha = max(0.0, min(1.0, 1.0 - confidence))
    idx = alpha * (len(ordered) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    frac = idx - lo
    quantile = ordered[lo] * (1.0 - frac) + ordered[hi] * frac
    return max(0.0, -quantile)


def parametric_var(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Parametric (Gaussian) Value at Risk (returned as positive loss fraction)."""
    if len(returns) < 2:
        return 0.0
    mu = _mean(returns)
    sigma = _sample_std(returns)
    z = Z_SCORE_95 if abs(confidence - 0.95) < 1e-4 else 1.6448536
    loss = -(mu - z * sigma)
    return max(0.0, loss)


def conditional_var(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Conditional VaR / Expected Shortfall at `confidence` level (positive loss fraction)."""
    if not returns:
        return 0.0
    var_threshold = -historical_var(returns, confidence)
    tail = [r for r in returns if r <= var_threshold]
    if not tail:
        return historical_var(returns, confidence)
    return max(0.0, -_mean(tail))


def pearson_correlation(x: Sequence[float | None], y: Sequence[float | None]) -> float | None:
    """Pearson correlation over positions where both series have a value.

    Series must already be aligned by date (see `align_to_base`); None marks a gap.
    """
    pairs = [(a, b) for a, b in zip(x, y, strict=False) if a is not None and b is not None]
    n = len(pairs)
    if n < 2:
        return None
    xs = [a for a, _ in pairs]
    ys = [b for _, b in pairs]
    mx = _mean(xs)
    my = _mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys, strict=False))
    den_x = math.sqrt(sum((a - mx) ** 2 for a in xs))
    den_y = math.sqrt(sum((b - my) ** 2 for b in ys))
    if den_x <= 1e-12 or den_y <= 1e-12:
        return None
    return max(-1.0, min(1.0, num / (den_x * den_y)))


def beta_alpha(
    asset_returns: Sequence[float],
    benchmark_returns: Sequence[float],
    annual_risk_free_rate: float = 0.1075,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
    *,
    asset_dates: Sequence[date] | None = None,
    benchmark_dates: Sequence[date] | None = None,
) -> tuple[float | None, float | None]:
    """Compute (Beta, annualized Jensen's Alpha) of `asset_returns` against `benchmark_returns`.

    With both date sequences the benchmark is aligned to the asset periods by date;
    without them the series are assumed to be already aligned (same length).
    """
    if asset_dates is not None and benchmark_dates is not None:
        a_ret, b_ret = _paired(
            asset_returns, align_to_base(asset_dates, benchmark_dates, benchmark_returns)
        )
    else:
        n = min(len(asset_returns), len(benchmark_returns))
        a_ret, b_ret = list(asset_returns[-n:]), list(benchmark_returns[-n:])
    n = len(a_ret)
    if n < 2:
        return None, None
    mb = _mean(b_ret)
    ma = _mean(a_ret)
    var_b = sum((b - mb) ** 2 for b in b_ret) / (n - 1)
    if var_b <= 1e-12:
        return None, None
    cov_ab = sum((a - ma) * (b - mb) for a, b in zip(a_ret, b_ret, strict=False)) / (n - 1)
    beta = cov_ab / var_b

    rf_periodic = (1.0 + annual_risk_free_rate) ** (1.0 / periods_per_year) - 1.0
    alpha_periodic = (ma - rf_periodic) - beta * (mb - rf_periodic)
    alpha_annual = alpha_periodic * periods_per_year
    return round(beta, 4), round(alpha_annual, 4)


def correlation_matrix(
    series_by_symbol: Mapping[str, Sequence[float | None]],
) -> dict[str, dict[str, float]]:
    """Symmetric Pearson correlation matrix of return series aligned to the same periods."""
    symbols = list(series_by_symbol.keys())
    matrix: dict[str, dict[str, float]] = {s: {} for s in symbols}
    for i, sym_a in enumerate(symbols):
        matrix[sym_a][sym_a] = 1.0
        for sym_b in symbols[i + 1 :]:
            corr = pearson_correlation(series_by_symbol[sym_a], series_by_symbol[sym_b])
            val = round(corr, 4) if corr is not None else 0.0
            matrix[sym_a][sym_b] = val
            matrix[sym_b][sym_a] = val
    return matrix


def build_base100_curve(
    dates: Sequence[date],
    returns: Sequence[float],
) -> list[dict[str, str | float]]:
    """Convert periodic returns into a normalized Base-100 wealth curve for UI charts."""
    if not dates:
        return []
    curve: list[dict[str, str | float]] = [{"date": dates[0].isoformat(), "value": 100.0}]
    level = 100.0
    for d, r in zip(dates[1:], returns, strict=False):
        level *= 1.0 + r
        curve.append({"date": d.isoformat(), "value": round(level, 4)})
    return curve


def analyze_return_series(
    returns: Sequence[float],
    *,
    benchmark_returns_map: Mapping[str, Sequence[float]] | None = None,
    annual_cdi_rate: float = 0.1075,
    annual_ipca_rate: float = 0.045,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
    dates: Sequence[date] | None = None,
    benchmark_dates_map: Mapping[str, Sequence[date]] | None = None,
) -> RiskReturnSummary:
    """Compute full statistical summary and compare against IBOV, IFIX, S&P 500, CDI, and IPCA.

    When `dates` and a benchmark's dates are given, the benchmark is aligned to the
    portfolio periods by date before computing its return, beta, alpha and correlation.
    """
    n = len(returns)
    cum_ret = cumulative_return(returns)
    ann_cagr = cagr(cum_ret, n, periods_per_year)
    years = n / periods_per_year if n > 0 else 0.0
    period_ipca = (1.0 + annual_ipca_rate) ** years - 1.0 if years > 0 else 0.0
    real_ret = real_return_vs_inflation(cum_ret, period_ipca)

    vol = annualized_volatility(returns, periods_per_year)
    sharpe = sharpe_ratio(returns, annual_cdi_rate, periods_per_year)
    sortino = sortino_ratio(returns, annual_cdi_rate, periods_per_year)
    dd_curve = drawdown_series(returns)
    mdd = min(dd_curve) if dd_curve else 0.0
    calmar = calmar_ratio(returns, periods_per_year)
    h_var = historical_var(returns, 0.95)
    p_var = parametric_var(returns, 0.95)
    c_var = conditional_var(returns, 0.95)

    comparisons: list[BenchmarkComparison] = []
    if benchmark_returns_map:
        for b_name, b_rets in benchmark_returns_map.items():
            if not b_rets:
                continue
            b_dates = (benchmark_dates_map or {}).get(b_name)
            if dates is not None and b_dates is not None:
                base_rets, b_aligned = _paired(returns, align_to_base(dates, b_dates, b_rets))
                if not b_aligned:
                    continue
            else:
                base_rets, b_aligned = list(returns), list(b_rets)
            b_cum = cumulative_return(b_aligned)
            beta, alpha = beta_alpha(base_rets, b_aligned, annual_cdi_rate, periods_per_year)
            corr = pearson_correlation(base_rets, b_aligned)
            comparisons.append(
                BenchmarkComparison(
                    benchmark=b_name,
                    benchmark_return=round(b_cum, 4),
                    excess_return=round(cum_ret - b_cum, 4),
                    beta=beta,
                    alpha_annual=alpha,
                    correlation=round(corr, 4) if corr is not None else None,
                )
            )

    # Always include synthetic CDI and IPCA period comparisons if not already in map
    existing_names = {c.benchmark.upper() for c in comparisons}
    if "CDI" not in existing_names and years > 0:
        cdi_cum = (1.0 + annual_cdi_rate) ** years - 1.0
        comparisons.append(
            BenchmarkComparison(
                benchmark="CDI",
                benchmark_return=round(cdi_cum, 4),
                excess_return=round(cum_ret - cdi_cum, 4),
            )
        )
    if "IPCA" not in existing_names and years > 0:
        comparisons.append(
            BenchmarkComparison(
                benchmark="IPCA",
                benchmark_return=round(period_ipca, 4),
                excess_return=round(cum_ret - period_ipca, 4),
            )
        )

    return RiskReturnSummary(
        observations=n,
        cumulative_return=round(cum_ret, 4),
        cagr=round(ann_cagr, 4),
        real_return_vs_ipca=round(real_ret, 4),
        annualized_volatility=round(vol, 4),
        sharpe_ratio=round(sharpe, 4),
        sortino_ratio=round(sortino, 4),
        max_drawdown=round(mdd, 4),
        calmar_ratio=round(calmar, 4),
        var_95_historical=round(h_var, 4),
        var_95_parametric=round(p_var, 4),
        cvar_95=round(c_var, 4),
        benchmarks=comparisons,
        drawdown_curve=[round(d, 4) for d in dd_curve],
    )


def accumulate_daily_rate_curve(
    dates: Sequence[date], percent_per_day: Sequence[float]
) -> list[dict[str, str | float]]:
    """Base-100 curve of a daily rate series such as the CDI (values in % per day).

    The rate of a day accrues from the first date on, so the first point is 100.
    """
    if not dates:
        return []
    curve: list[dict[str, str | float]] = [{"date": dates[0].isoformat(), "value": 100.0}]
    level = 100.0
    for d, rate in zip(dates[1:], percent_per_day[1:], strict=False):
        level *= 1.0 + rate / 100.0
        curve.append({"date": d.isoformat(), "value": round(level, 4)})
    return curve
