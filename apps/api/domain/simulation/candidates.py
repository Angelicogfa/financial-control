"""Candidate assets outside the portfolio (Phase 33.7, layer D; design 5 and 6.2).

Using a candidate's own history as its future would extrapolate luck. Each candidate is
modelled against its class: r_asset = α + β · r_class + ε, on monthly returns in excess of
the CDI (the same space as layer B).

- α (the asset's "extra") gets a hierarchical prior N(0, τ²_class), τ² estimated by empirical
  Bayes from every asset of the class with history: a short or noisy history leaves almost
  no α. β gets a prior N(1, 0.5²), which shrinks extreme betas estimated from few data.
- ε is drawn in blocks from the asset's own residuals (its tails and volatility).
- r_class comes from the layer B paths (generator mixture and rate scenarios).
- A rupture event (design 10.4) with a declared annual probability: the history of a
  survivor does not show that risk.

The marginal effect of adding a candidate is measured on the *same* paths with and without
it (common random numbers): Δ final wealth, Δ goal probability, Δ CVaR, Δ drawdown, Δ
diversification ratio and Δ income, with P(improvement) and its credibility interval, plus
the stability of the ranking when the paths are resampled. Nothing here is a purchase: the
output is a list of candidates *to investigate*.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from domain.shared.enums import ArcaClass, AssetType
from domain.simulation.bayes import credible_interval
from domain.simulation.market import MarketHistory, month_ends
from domain.simulation.scenarios import (
    CASH_INDEX,
    CLASS_ORDER,
    ClassSample,
    stationary_bootstrap_indices,
)

CANDIDATE_PREFIX = "candidate:"
SUMMARY_KEY = "candidates:summary"
MAX_CANDIDATES = 20
MIN_HISTORY_MONTHS = 36
BETA_PRIOR_SD = 0.5
# Without enough assets in a class to estimate τ: a 3% a year spread of true alphas.
DEFAULT_ALPHA_SD_MONTHLY = 0.03 / 12.0
MIN_ASSETS_FOR_TAU = 3
TOP_K = 5
RANK_RESAMPLES = 100
RISK_MONTHS = 12

# Decision 9 (design 10.4): annual rupture probability by credit zone; loss on the event.
RUPTURE_ANNUAL: dict[str, float] = {
    "STRESS": 0.05,
    "GRAY": 0.01,
    "SAFE": 0.002,
    "NO_DATA": 0.01,
    "FII": 0.005,
    "ETF": 0.0,  # a diversified fund does not default as one company
}
RUPTURE_LOSS = 0.55
RUPTURE_STRESS_LOSS = 0.90


class CandidateSource:
    WATCHLIST = "WATCHLIST"
    SCREENER = "SCREENER"


FUND_TYPES = frozenset({AssetType.ETF_BR, AssetType.ETF_INTL})


def rupture_zone(asset_type: AssetType, z_zone: str | None = None) -> str:
    """The rupture class of a candidate: FII, ETF, or the Z''-score zone (no data: 1%)."""
    if asset_type in (AssetType.FII, AssetType.REIT):
        return "FII"
    if asset_type in FUND_TYPES:
        return "ETF"
    return z_zone if z_zone in RUPTURE_ANNUAL else "NO_DATA"


@dataclass(frozen=True)
class CandidateSpec:
    """A candidate as frozen at request time (filters already applied)."""

    ticker: str
    name: str
    arca_class: ArcaClass
    asset_type: AssetType
    source: str = CandidateSource.WATCHLIST
    eligible: bool | None = None  # None: no checklist evaluation (screener)
    valuation_verdict: str | None = None
    dividend_yield: float | None = None  # annual fraction
    suspicious: bool = False
    zone: str = "NO_DATA"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["arca_class"] = self.arca_class.value
        data["asset_type"] = self.asset_type.value
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CandidateSpec:
        return cls(
            ticker=str(data["ticker"]),
            name=str(data.get("name", data["ticker"])),
            arca_class=ArcaClass(data["arca_class"]),
            asset_type=AssetType(data["asset_type"]),
            source=str(data.get("source", CandidateSource.WATCHLIST)),
            eligible=data.get("eligible"),
            valuation_verdict=data.get("valuation_verdict"),
            dividend_yield=data.get("dividend_yield"),
            suspicious=bool(data.get("suspicious", False)),
            zone=str(data.get("zone", "NO_DATA")),
        )


# --- factor model --------------------------------------------------------------------------------


def monthly_excess(
    history: MarketHistory, ticker: str, sample: ClassSample
) -> tuple[np.ndarray, np.ndarray]:
    """The asset's monthly excess over the CDI on the sample months it covers, and a mask."""
    series = history.series.get(ticker.upper())
    mask = np.zeros(sample.size, dtype=bool)
    excess = np.zeros(sample.size)
    if series is None or len(series.dates) < 2:
        return excess, mask
    ends = month_ends(series.dates[0], series.dates[-1])
    levels = {(d.year, d.month): series.last_on_or_before(d) for d in ends}
    for i, month in enumerate(sample.months):
        prev = (month.year - 1, 12) if month.month == 1 else (month.year, month.month - 1)
        a, b = levels.get(prev), levels.get((month.year, month.month))
        if a and b and a > 0:
            mask[i] = True
            excess[i] = (b / a) / (1.0 + sample.cdi[i]) - 1.0
    return excess, mask


@dataclass(frozen=True)
class FactorFit:
    ticker: str
    arca_class: ArcaClass
    months: int
    alpha: float  # monthly
    alpha_se: float
    beta: float
    beta_se: float
    residuals: np.ndarray = field(repr=False, compare=False)
    alpha_post: float = 0.0
    alpha_post_sd: float = 0.0
    beta_post: float = 1.0
    beta_post_sd: float = BETA_PRIOR_SD
    shrinkage: float = 1.0  # share of α̂ removed by the prior (1 = all)
    alpha_prior_mean: float = 0.0  # where α is pulled to (the valuation signal, Phase 42.3)


def ols_fit(y: np.ndarray, x: np.ndarray) -> tuple[float, float, float, float, np.ndarray]:
    """α, se(α), β, se(β) and residuals of y = α + β x + ε."""
    n = y.size
    design = np.column_stack([np.ones(n), x])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    resid = y - design @ coef
    dof = max(n - 2, 1)
    sigma2 = float(resid @ resid) / dof
    cov = sigma2 * np.linalg.pinv(design.T @ design)
    return (
        float(coef[0]),
        float(math.sqrt(max(cov[0, 0], 0.0))),
        float(coef[1]),
        float(math.sqrt(max(cov[1, 1], 0.0))),
        resid,
    )


def fit_asset(
    ticker: str,
    arca_class: ArcaClass,
    history: MarketHistory,
    sample: ClassSample,
    *,
    min_months: int = MIN_HISTORY_MONTHS,
) -> FactorFit | None:
    """OLS against the class proxy over the months both exist (None below `min_months`)."""
    excess, mask = monthly_excess(history, ticker, sample)
    if mask.sum() < min_months:
        return None
    k = CLASS_ORDER.index(arca_class)
    alpha, alpha_se, beta, beta_se, resid = ols_fit(excess[mask], sample.excess[mask, k])
    return FactorFit(ticker, arca_class, int(mask.sum()), alpha, alpha_se, beta, beta_se, resid)


def class_tau(fits: Sequence[FactorFit]) -> float:
    """Empirical Bayes sd of the true alphas of a class: var(α̂) minus the mean noise."""
    if len(fits) < MIN_ASSETS_FOR_TAU:
        return DEFAULT_ALPHA_SD_MONTHLY
    alphas = np.array([f.alpha for f in fits])
    noise = float(np.mean([f.alpha_se**2 for f in fits]))
    return math.sqrt(max(float(np.var(alphas, ddof=1)) - noise, 0.0))


def shrink(fit: FactorFit, tau: float, prior_mean: float = 0.0) -> FactorFit:
    """Normal-normal posteriors: α to `prior_mean` (0 without a signal) with prior sd τ, β to 1
    with prior sd 0.5."""
    se2 = max(fit.alpha_se**2, 1e-18)
    tau2 = tau * tau
    weight = tau2 / (tau2 + se2) if tau2 > 0 else 0.0
    alpha_post = weight * fit.alpha + (1.0 - weight) * prior_mean
    alpha_post_sd = math.sqrt(tau2 * se2 / (tau2 + se2)) if tau2 > 0 else 0.0
    b_prec = 1.0 / max(fit.beta_se**2, 1e-18)
    p_prec = 1.0 / BETA_PRIOR_SD**2
    beta_post = (fit.beta * b_prec + 1.0 * p_prec) / (b_prec + p_prec)
    beta_post_sd = math.sqrt(1.0 / (b_prec + p_prec))
    return FactorFit(
        fit.ticker,
        fit.arca_class,
        fit.months,
        fit.alpha,
        fit.alpha_se,
        fit.beta,
        fit.beta_se,
        fit.residuals,
        alpha_post=alpha_post,
        alpha_post_sd=alpha_post_sd,
        beta_post=beta_post,
        beta_post_sd=beta_post_sd,
        shrinkage=round(1.0 - weight, 4),
        alpha_prior_mean=prior_mean,
    )


def candidate_excess(
    fit: FactorFit,
    class_excess: np.ndarray,
    *,
    rupture_annual: float,
    rupture_loss: float,
    mean_block: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """(paths, horizon) monthly excess of the candidate on the layer B class paths."""
    paths, horizon = class_excess.shape
    alpha = rng.normal(fit.alpha_post, fit.alpha_post_sd, paths)[:, None]
    beta = rng.normal(fit.beta_post, fit.beta_post_sd, paths)[:, None]
    idx = stationary_bootstrap_indices(fit.residuals.size, horizon, paths, mean_block, rng)
    out = alpha + beta * class_excess + fit.residuals[idx]
    if rupture_annual > 0:
        monthly = 1.0 - (1.0 - rupture_annual) ** (1.0 / 12.0)
        hit = rng.random((paths, horizon)) < monthly
        out = np.where(hit, (1.0 + out) * (1.0 - rupture_loss) - 1.0, out)
    return np.maximum(out, -0.99)


# --- portfolio effects ---------------------------------------------------------------------------


def blend(excess: np.ndarray, column: int, candidate: np.ndarray, share: float) -> np.ndarray:
    """Layer B excess paths with `share` of a class replaced by the candidate."""
    out = excess.copy()
    out[:, :, column] = (1.0 - share) * excess[:, :, column] + share * candidate
    return out


def static_returns(
    excess: np.ndarray, weights: np.ndarray, cdi_m: float, cash_m: float
) -> np.ndarray:
    """(paths, horizon) monthly total return of a portfolio held at fixed class weights."""
    total = (1.0 + excess) * (1.0 + cdi_m) - 1.0
    total[:, :, CASH_INDEX] = cash_m
    return total @ weights


def cvar(values: np.ndarray, level: float = 0.95) -> float:
    """Mean of the worst (1 - level) share (a loss is negative)."""
    cut = np.quantile(values, 1.0 - level)
    tail = values[values <= cut]
    return float(tail.mean()) if tail.size else float(cut)


def max_drawdowns(monthly: np.ndarray) -> np.ndarray:
    growth = np.cumprod(1.0 + monthly, axis=1)
    peak = np.maximum.accumulate(growth, axis=1)
    return (growth / peak - 1.0).min(axis=1)


def diversification_ratio(components: np.ndarray, weights: np.ndarray) -> float:
    """Choueifaty: Σ w σ / σ_portfolio, from pooled monthly returns (columns = components)."""
    flat = components.reshape(-1, components.shape[-1])
    cov = np.cov(flat, rowvar=False)
    sd = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    port = float(np.sqrt(max(weights @ cov @ weights, 1e-18)))
    return float((weights * sd).sum() / port)


@dataclass(frozen=True)
class CandidateEffect:
    """Distribution of the change in each measure when the candidate is added."""

    ticker: str
    share_in_class: float
    weight: float  # of the whole portfolio
    delta_final_wealth: float  # median, today's money
    p_improve: float
    p_improve_low: float
    p_improve_high: float
    delta_goal_probability: float | None
    delta_cvar_12m: float  # positive = smaller tail loss
    delta_drawdown: float  # median; positive = shallower
    delta_diversification: float
    delta_income_yield: float  # annual, on the whole portfolio
    top_k_share: float = 0.0  # stability: share of resamples in the top 5
    rank: int = 0


def ranking_stability(
    deltas: np.ndarray, *, resamples: int, rng: np.random.Generator, top_k: int = TOP_K
) -> np.ndarray:
    """Share of path resamples in which each candidate (row) ranks in the top `top_k`."""
    count, paths = deltas.shape
    hits = np.zeros(count)
    k = min(top_k, count)
    for _ in range(resamples):
        idx = rng.integers(0, paths, paths)
        medians = np.median(deltas[:, idx], axis=1)
        hits[np.argsort(-medians)[:k]] += 1
    return hits / resamples


def p_improvement(diff: np.ndarray) -> tuple[float, float, float]:
    n = diff.size
    k = float((diff > 0).sum())
    low, high = credible_interval(k, n)
    return round(k / n, 4), low, high
