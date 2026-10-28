"""Concentration and risk diversification measures (items 29.1 and 29.2).

- Concentration: Herfindahl-Hirschman Index (HHI = sum of squared weights) and the
  effective number of holdings (1 / HHI) for any grouping of the portfolio.
- Covariance: Ledoit-Wolf shrinkage of the correlation matrix towards the identity, then
  rescaled by the sample volatilities, so assets keep their own risk while noisy
  correlations shrink. Near-riskless assets (CDI-like, zero sample volatility) get zero
  variance and covariance.
- Choueifaty diversification ratio: weighted average volatility / portfolio volatility.
- Euler decomposition: the risk contribution of asset i is w_i (Sigma w)_i / sigma_p, and the
  contributions add up to sigma_p.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from domain.portfolio.services.analytics import TRADING_DAYS_PER_YEAR

# Daily standard deviation below 0.5% a year: CDI-like assets are treated as riskless.
RISKLESS_STD = 0.005 / math.sqrt(TRADING_DAYS_PER_YEAR)


@dataclass(frozen=True)
class Concentration:
    """HHI and effective number of a weight distribution (weights normalized to 1)."""

    hhi: float
    effective_count: float
    weights: dict[str, float]


@dataclass(frozen=True)
class CovarianceEstimate:
    """Annualized shrunk covariance of the assets in `names`."""

    names: list[str]
    covariance: np.ndarray
    correlation: np.ndarray
    volatilities: np.ndarray
    shrinkage: float
    observations: int


@dataclass(frozen=True)
class RiskDecomposition:
    """Portfolio volatility, diversification ratio and Euler risk share per asset."""

    volatility: float
    diversification_ratio: float | None
    risk_shares: dict[str, float]
    weights: dict[str, float]


def concentration(values: Mapping[str, float]) -> Concentration | None:
    """HHI and effective number of the positive `values` (grouped amounts, not weights)."""
    positive = {k: v for k, v in values.items() if v > 0}
    total = sum(positive.values())
    if total <= 0:
        return None
    weights = {k: v / total for k, v in sorted(positive.items(), key=lambda kv: -kv[1])}
    hhi = sum(w * w for w in weights.values())
    return Concentration(hhi=round(hhi, 4), effective_count=round(1.0 / hhi, 2), weights=weights)


def top_weight(weights: Mapping[str, float], count: int) -> float:
    """Combined weight of the `count` largest entries."""
    return sum(sorted(weights.values(), reverse=True)[:count])


def ledoit_wolf_shrinkage(standardized: np.ndarray) -> tuple[np.ndarray, float]:
    """Ledoit-Wolf (2004) estimate towards a scaled identity for centered data (T x N)."""
    t, n = standardized.shape
    x = standardized - standardized.mean(axis=0)
    emp_cov = x.T @ x / t
    mu = float(np.trace(emp_cov)) / n
    x2 = x**2
    emp_cov_trace = x2.sum(axis=0) / t
    beta_sum = float((x2.T @ x2).sum())
    delta_sum = float((emp_cov**2).sum())
    beta = (beta_sum / t - delta_sum) / (n * t)
    delta = (delta_sum - 2.0 * mu * float(emp_cov_trace.sum()) + n * mu**2) / n
    beta = min(beta, delta)
    shrinkage = 0.0 if delta <= 0 or beta <= 0 else beta / delta
    shrunk = (1.0 - shrinkage) * emp_cov + shrinkage * mu * np.eye(n)
    return shrunk, shrinkage


def estimate_covariance(
    series: Mapping[str, Sequence[float | None]],
    *,
    min_observations: int,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
) -> CovarianceEstimate | None:
    """Shrunk annualized covariance of aligned periodic returns (None gaps count as 0).

    Assets with fewer than `min_observations` known returns are left out.
    """
    names = [
        n for n, values in series.items() if sum(v is not None for v in values) >= min_observations
    ]
    if not names:
        return None
    length = min(len(series[n]) for n in names)
    if length < min_observations:
        return None
    data = np.array(
        [[(series[n][t] or 0.0) for n in names] for t in range(length)],
        dtype=float,
    )
    std = data.std(axis=0, ddof=1)
    risky = std > RISKLESS_STD
    k = len(names)
    correlation = np.eye(k)
    shrinkage = 0.0
    risky_idx = np.flatnonzero(risky)
    if len(risky_idx) >= 2:
        standardized = (data[:, risky_idx] - data[:, risky_idx].mean(axis=0)) / std[risky_idx]
        shrunk, shrinkage = ledoit_wolf_shrinkage(standardized)
        diag = np.sqrt(np.clip(np.diag(shrunk), 1e-18, None))
        sub_corr = shrunk / np.outer(diag, diag)
        for a, i in enumerate(risky_idx):
            for b, j in enumerate(risky_idx):
                correlation[i, j] = sub_corr[a, b]
    for i in range(k):
        if not risky[i]:
            correlation[i, :] = 0.0
            correlation[:, i] = 0.0
            correlation[i, i] = 1.0
    vols = np.where(risky, std, 0.0) * math.sqrt(periods_per_year)
    covariance = correlation * np.outer(vols, vols)
    return CovarianceEstimate(
        names=names,
        covariance=covariance,
        correlation=correlation,
        volatilities=vols,
        shrinkage=round(shrinkage, 4),
        observations=length,
    )


def decompose_risk(estimate: CovarianceEstimate, values: Mapping[str, float]) -> RiskDecomposition:
    """Volatility, Choueifaty ratio and Euler risk shares of the weights implied by `values`."""
    amounts = np.array([max(values.get(n, 0.0), 0.0) for n in estimate.names], dtype=float)
    total = float(amounts.sum())
    if total <= 0:
        return RiskDecomposition(0.0, None, {}, {})
    w = amounts / total
    marginal = estimate.covariance @ w
    variance = float(w @ marginal)
    sigma = math.sqrt(max(variance, 0.0))
    weights = {n: round(float(w[i]), 4) for i, n in enumerate(estimate.names)}
    if sigma <= 1e-12:
        return RiskDecomposition(0.0, None, {n: 0.0 for n in estimate.names}, weights)
    shares = {
        n: round(float(w[i] * marginal[i] / variance), 4) for i, n in enumerate(estimate.names)
    }
    ratio = float(w @ estimate.volatilities) / sigma
    return RiskDecomposition(
        volatility=round(sigma, 4),
        diversification_ratio=round(ratio, 4),
        risk_shares=shares,
        weights=weights,
    )


def sample_correlations(
    series: Mapping[str, Sequence[float | None]], names: Sequence[str]
) -> dict[tuple[str, str], float]:
    """Pairwise Pearson correlation of risky assets over their common known periods."""
    out: dict[tuple[str, str], float] = {}
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            pairs = [
                (x, y)
                for x, y in zip(series[a], series[b], strict=False)
                if x is not None and y is not None
            ]
            if len(pairs) < 3:
                continue
            xs = np.array([p[0] for p in pairs])
            ys = np.array([p[1] for p in pairs])
            if xs.std() <= RISKLESS_STD or ys.std() <= RISKLESS_STD:
                continue
            out[(a, b)] = round(float(np.corrcoef(xs, ys)[0, 1]), 4)
    return out
