"""Bayesian layer of the simulation (Phase 33.6; design 6.1, 6.3, 6.6 and decision 8).

Closed forms only, in numpy (no MCMC on the main path):
- Bayes-Stein (Jorion, 1986) sets how strongly the class means are pulled to the target of
  conservative premiums over the CDI; the strength becomes the prior weight in equivalent
  months, always reported (risk R15).
- Normal-inverse-Wishart posterior of the mean and covariance of the monthly *log* excess
  returns (log(1 + excess)), with the prior covariance at the Ledoit-Wolf estimate. Working in
  logs makes the target a geometric premium ("CDI + 3% a year"), as the decision states.
- Parameter draws: covariance from the inverse Wishart (Bartlett decomposition), mean from
  the normal given it; each path then has its own parameters.
- Beta quantiles by numerical integration, for credibility intervals of probabilities.
- Stacking weights of predictive densities (Yao, Vehtari, Simpson & Gelman, 2018), by the
  EM fixed point of the mixture weights, which maximizes the mixture's log score.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from domain.portfolio.services.diversification import ledoit_wolf_shrinkage
from domain.shared.enums import ArcaClass

# Decision 8 (design 10.3): geometric premium over the CDI the means are shrunk to.
PRIOR_PREMIUM_ANNUAL: dict[ArcaClass, float] = {
    ArcaClass.ACOES: 0.03,
    ArcaClass.ATIVOS_INTERNACIONAIS: 0.03,
    ArcaClass.REAL_ESTATE: 0.02,
}
# A sample mean equal to the target would give an infinite prior weight.
MAX_PRIOR_MONTHS = 600.0
CREDIBILITY = 0.90


def prior_mean(classes: Sequence[ArcaClass]) -> np.ndarray:
    """Monthly log excess of the decision 8 premiums."""
    return np.array([math.log1p(PRIOR_PREMIUM_ANNUAL[c]) / 12.0 for c in classes])


def ledoit_wolf_covariance(x: np.ndarray) -> np.ndarray:
    """Covariance of the columns of x (T x K) with the correlation shrunk by Ledoit-Wolf."""
    std = x.std(axis=0, ddof=1)
    if x.shape[1] == 1:
        return np.array([[float(std[0]) ** 2]])
    standardized = (x - x.mean(axis=0)) / np.where(std > 0, std, 1.0)
    shrunk, _ = ledoit_wolf_shrinkage(standardized)
    diag = np.sqrt(np.clip(np.diag(shrunk), 1e-18, None))
    correlation = shrunk / np.outer(diag, diag)
    return correlation * np.outer(std, std)


def bayes_stein_weight(x: np.ndarray, target: np.ndarray) -> float:
    """Jorion's w = (N + 2) / ((N + 2) + T (x̄ - μ0)' Σ⁻¹ (x̄ - μ0)), in [0, 1]."""
    t, n = x.shape
    if t <= n + 2:
        return 1.0
    sample_cov = np.cov(x, rowvar=False, ddof=1).reshape(n, n) * (t - 1) / (t - n - 2)
    d = x.mean(axis=0) - target
    # Pseudo-inverse: a class that never moved carries no information on the mean.
    q = float(t * d @ np.linalg.pinv(sample_cov) @ d)
    return (n + 2) / ((n + 2) + q)


@dataclass(frozen=True)
class NiwPosterior:
    """Posterior of (μ, Σ) of the monthly log excess returns of `classes`."""

    classes: tuple[ArcaClass, ...]
    mean: np.ndarray  # μn
    kappa: float  # κn = κ0 + T
    nu: float  # νn = ν0 + T
    scale: np.ndarray  # Ψn
    prior_mean: np.ndarray  # μ0
    prior_months: float  # κ0, the prior weight in equivalent months of data
    sample_mean: np.ndarray
    months: int  # T

    @property
    def expected_covariance(self) -> np.ndarray:
        return self.scale / (self.nu - len(self.classes) - 1)

    def annual_premium(self, mean: np.ndarray | None = None) -> np.ndarray:
        """Geometric premium a year of a monthly log excess (the posterior mean by default)."""
        return np.expm1(12.0 * (self.mean if mean is None else mean))


def niw_posterior(
    x: np.ndarray,
    classes: Sequence[ArcaClass],
    *,
    target: np.ndarray | None = None,
    prior_cov: np.ndarray | None = None,
    prior_months: float | None = None,
) -> NiwPosterior:
    """Conjugate update of a normal-inverse-Wishart prior with T monthly observations.

    Prior: μ | Σ ~ N(μ0, Σ / κ0), Σ ~ IW(ν0, Ψ0) with ν0 = K + 2 and Ψ0 = the Ledoit-Wolf
    covariance (so E[Σ] = Ψ0 a priori). κ0 comes from Bayes-Stein unless given.
    """
    t, k = x.shape
    mu0 = prior_mean(classes) if target is None else target
    if prior_cov is None:
        prior_cov = ledoit_wolf_covariance(x)
    if prior_months is None:
        w = bayes_stein_weight(x, mu0)
        prior_months = MAX_PRIOR_MONTHS if w >= 1.0 else min(w * t / (1.0 - w), MAX_PRIOR_MONTHS)
    kappa0, nu0 = max(prior_months, 1e-9), k + 2.0
    xbar = x.mean(axis=0) if t else np.zeros(k)
    scatter = (x - xbar).T @ (x - xbar) if t else np.zeros((k, k))
    kappa = kappa0 + t
    d = xbar - mu0
    return NiwPosterior(
        classes=tuple(classes),
        mean=(kappa0 * mu0 + t * xbar) / kappa,
        kappa=kappa,
        nu=nu0 + t,
        # A tiny ridge keeps the scale positive definite when a column never moves.
        scale=prior_cov * (nu0 - k - 1)
        + scatter
        + (kappa0 * t / kappa) * np.outer(d, d)
        + np.eye(k) * 1e-12,
        prior_mean=mu0,
        prior_months=round(float(prior_months), 2),
        sample_mean=xbar,
        months=t,
    )


def sample_wishart(nu: float, scale: np.ndarray, size: int, rng: np.random.Generator) -> np.ndarray:
    """(size, K, K) draws of Wishart(ν, V) by the Bartlett decomposition."""
    k = scale.shape[0]
    chol = np.linalg.cholesky(scale)
    a = np.zeros((size, k, k))
    for i in range(k):
        a[:, i, i] = np.sqrt(rng.chisquare(nu - i, size))
        a[:, i, :i] = rng.standard_normal((size, i))
    la = chol @ a
    return la @ np.transpose(la, (0, 2, 1))


def sample_inverse_wishart(
    nu: float, scale: np.ndarray, size: int, rng: np.random.Generator
) -> np.ndarray:
    """(size, K, K) draws of IW(ν, Ψ): the inverse of Wishart(ν, Ψ⁻¹)."""
    return np.linalg.inv(sample_wishart(nu, np.linalg.inv(scale), size, rng))


def sample_parameters(
    posterior: NiwPosterior, size: int, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """`size` draws of (μ, Σ) from the posterior: Σ first, then μ | Σ."""
    covs = sample_inverse_wishart(posterior.nu, posterior.scale, size, rng)
    chol = np.linalg.cholesky(covs / posterior.kappa)
    z = rng.standard_normal((size, len(posterior.classes)))
    mus = posterior.mean + np.einsum("sij,sj->si", chol, z)
    return mus, covs


def normal_log_paths(
    posterior: NiwPosterior, paths: int, horizon: int, rng: np.random.Generator
) -> np.ndarray:
    """(paths, horizon, K) monthly log excess returns, each path with its own (μ, Σ)."""
    mus, covs = sample_parameters(posterior, paths, rng)
    chol = np.linalg.cholesky(covs)
    z = rng.standard_normal((paths, horizon, len(posterior.classes)))
    return mus[:, None, :] + np.einsum("pij,phj->phi", chol, z)


def beta_quantiles(
    a: float, b: float, probs: Sequence[float], *, grid: int = 20_001
) -> list[float]:
    """Quantiles of Beta(a, b) (a, b >= 1) from its numerically integrated CDF."""
    x = np.linspace(0.0, 1.0, grid)
    log_norm = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    with np.errstate(divide="ignore"):
        # An exponent of zero keeps the density finite at the edge (0 x log 0 = 0).
        left = (a - 1.0) * np.log(x) if a != 1.0 else np.zeros_like(x)
        right = (b - 1.0) * np.log1p(-x) if b != 1.0 else np.zeros_like(x)
    log_pdf = log_norm + left + right
    pdf = np.exp(np.where(np.isfinite(log_pdf), log_pdf, -np.inf))
    cdf = np.concatenate([[0.0], np.cumsum((pdf[1:] + pdf[:-1]) / 2.0 * np.diff(x))])
    cdf /= cdf[-1]
    return [float(np.interp(p, cdf, x)) for p in probs]


def credible_interval(
    successes: float, trials: float, level: float = CREDIBILITY
) -> tuple[float, float]:
    """Equal-tailed interval of Beta(k + 1, n - k + 1): a rate's posterior under a flat prior."""
    tail = (1.0 - level) / 2.0
    low, high = beta_quantiles(successes + 1.0, trials - successes + 1.0, (tail, 1.0 - tail))
    return round(low, 4), round(high, 4)


def stacking_weights(densities: np.ndarray, *, iterations: int = 1000) -> np.ndarray:
    """Weights on the simplex maximizing Σ_i log Σ_g w_g p_g(y_i) (rows: cases, columns: models)."""
    n, g = densities.shape
    w = np.full(g, 1.0 / g)
    p = np.clip(densities, 1e-300, None)
    for _ in range(iterations):
        mix = p @ w
        new = w * (p / mix[:, None]).mean(axis=0)
        if np.abs(new - w).max() < 1e-10:
            w = new
            break
        w = new
    return w / w.sum()
