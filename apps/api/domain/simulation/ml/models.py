"""Density forecasts of next month's portfolio return: regime and risk models (Phase 33.9).

Every model answers the same question, so they can be compared by the log score: given the
months up to t - 1, what is the density of the return in month t?

- `NormalReference`: N(mean, variance) of the history so far (the simple reference).
- `GaussianHMM`: hidden Markov model with K Gaussian regimes, fitted by EM (Baum-Welch with
  scaled forward-backward); the forecast mixes the regimes by the filtered probability of
  each one next month. The filter is Bayesian: P(regime | history).
- `GaussianMixture`: K Gaussian components without memory (EM); a regime model that ignores
  the order of the months.
- `Ewma`: the RiskMetrics variance recursion with decay λ; mean of the history so far.
- `Garch11`: GARCH(1,1) with variance targeting, (α, β) by maximum likelihood on a grid.

Fits are refreshed every `refit_every` months; in between, the filters run forward with the
parameters of the last fit, as a model used in practice would.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

VAR_FLOOR = 1e-8
LOG_2PI = math.log(2.0 * math.pi)


def normal_logpdf(y: float, mean: float, var: float) -> float:
    var = max(var, VAR_FLOOR)
    return -0.5 * (LOG_2PI + math.log(var) + (y - mean) ** 2 / var)


def mixture_logpdf(
    y: float, weights: np.ndarray, means: np.ndarray, variances: np.ndarray
) -> float:
    variances = np.maximum(variances, VAR_FLOOR)
    logs = np.log(np.maximum(weights, 1e-300)) - 0.5 * (
        LOG_2PI + np.log(variances) + (y - means) ** 2 / variances
    )
    top = float(logs.max())
    return top + math.log(float(np.exp(logs - top).sum()))


# --- Gaussian HMM --------------------------------------------------------------------------------


@dataclass
class HmmParams:
    start: np.ndarray  # (K,)
    transition: np.ndarray  # (K, K), rows sum to 1
    means: np.ndarray  # (K,)
    variances: np.ndarray  # (K,)
    loglik: float = float("-inf")


def _emissions(y: np.ndarray, means: np.ndarray, variances: np.ndarray) -> np.ndarray:
    variances = np.maximum(variances, VAR_FLOOR)
    return np.exp(
        -0.5
        * (
            LOG_2PI
            + np.log(variances)[None, :]
            + (y[:, None] - means[None, :]) ** 2 / variances[None, :]
        )
    )


def _forward(y: np.ndarray, p: HmmParams) -> tuple[np.ndarray, np.ndarray]:
    """Scaled forward pass: filtered probabilities (T, K) and scale factors (T,)."""
    b = np.maximum(_emissions(y, p.means, p.variances), 1e-300)
    t_len, k = b.shape
    alpha = np.empty((t_len, k))
    scale = np.empty(t_len)
    a = p.start * b[0]
    scale[0] = a.sum()
    alpha[0] = a / scale[0]
    for t in range(1, t_len):
        a = (alpha[t - 1] @ p.transition) * b[t]
        scale[t] = a.sum()
        alpha[t] = a / scale[t]
    return alpha, scale


def fit_hmm(y: np.ndarray, states: int, *, iterations: int = 200, tol: float = 1e-6) -> HmmParams:
    """Baum-Welch EM for a K-state Gaussian HMM (initialized by quantiles, sticky regimes)."""
    k = states
    qs = np.quantile(y, np.linspace(0.15, 0.85, k))
    p = HmmParams(
        start=np.full(k, 1.0 / k),
        transition=np.full((k, k), 0.1 / max(k - 1, 1)) + np.eye(k) * (0.9 - 0.1 / max(k - 1, 1)),
        means=qs.astype(float),
        variances=np.full(k, float(np.var(y)) or VAR_FLOOR),
    )
    previous = float("-inf")
    for _ in range(iterations):
        b = np.maximum(_emissions(y, p.means, p.variances), 1e-300)
        alpha, scale = _forward(y, p)
        t_len = y.size
        beta = np.empty_like(alpha)
        beta[-1] = 1.0
        for t in range(t_len - 2, -1, -1):
            beta[t] = (p.transition @ (b[t + 1] * beta[t + 1])) / scale[t + 1]
        gamma = alpha * beta
        gamma /= gamma.sum(axis=1, keepdims=True)
        xi = (
            alpha[:-1, :, None]
            * p.transition[None, :, :]
            * (b[1:] * beta[1:])[:, None, :]
            / scale[1:, None, None]
        )
        weights = gamma.sum(axis=0)
        p.start = gamma[0]
        trans = xi.sum(axis=0)
        p.transition = trans / np.maximum(trans.sum(axis=1, keepdims=True), 1e-300)
        p.means = (gamma * y[:, None]).sum(axis=0) / np.maximum(weights, 1e-300)
        p.variances = np.maximum(
            (gamma * (y[:, None] - p.means[None, :]) ** 2).sum(axis=0)
            / np.maximum(weights, 1e-300),
            VAR_FLOOR,
        )
        loglik = float(np.log(scale).sum())
        p.loglik = loglik
        if abs(loglik - previous) < tol:
            break
        previous = loglik
    order = np.argsort(p.means)  # state 0 = the worst regime
    p.start = p.start[order]
    p.transition = p.transition[np.ix_(order, order)]
    p.means = p.means[order]
    p.variances = p.variances[order]
    return p


def hmm_filter(y: np.ndarray, p: HmmParams) -> np.ndarray:
    """P(regime at t | months up to t) for every t."""
    return _forward(y, p)[0]


# --- Gaussian mixture ---------------------------------------------------------------------------


@dataclass
class MixtureParams:
    weights: np.ndarray
    means: np.ndarray
    variances: np.ndarray


def fit_mixture(
    y: np.ndarray, components: int, *, iterations: int = 300, tol: float = 1e-8
) -> MixtureParams:
    k = components
    p = MixtureParams(
        weights=np.full(k, 1.0 / k),
        means=np.quantile(y, np.linspace(0.15, 0.85, k)).astype(float),
        variances=np.full(k, float(np.var(y)) or VAR_FLOOR),
    )
    previous = float("-inf")
    for _ in range(iterations):
        dens = np.maximum(_emissions(y, p.means, p.variances) * p.weights[None, :], 1e-300)
        total = dens.sum(axis=1, keepdims=True)
        resp = dens / total
        n_k = np.maximum(resp.sum(axis=0), 1e-300)
        p.weights = n_k / y.size
        p.means = (resp * y[:, None]).sum(axis=0) / n_k
        p.variances = np.maximum((resp * (y[:, None] - p.means) ** 2).sum(axis=0) / n_k, VAR_FLOOR)
        loglik = float(np.log(total).sum())
        if abs(loglik - previous) < tol:
            break
        previous = loglik
    return p


# --- risk models -----------------------------------------------------------------------------


def garch_variances(y: np.ndarray, mean: float, omega: float, a: float, b: float) -> np.ndarray:
    """σ²_t for t = 0..T (σ²_T is the forecast after the last observation)."""
    var = np.empty(y.size + 1)
    var[0] = omega / max(1.0 - a - b, 1e-6)
    for t in range(y.size):
        var[t + 1] = omega + a * (y[t] - mean) ** 2 + b * var[t]
    return var


def fit_garch(y: np.ndarray) -> tuple[float, float, float, float]:
    """(mean, ω, α, β) by maximum likelihood on a grid, with ω set by variance targeting."""
    mean = float(y.mean())
    sample_var = float(y.var()) or VAR_FLOOR
    best = (float("-inf"), 0.05, 0.9)
    for a in (0.02, 0.05, 0.08, 0.12, 0.16, 0.2):
        for b in (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.94, 0.97):
            if a + b >= 0.995:
                continue
            omega = sample_var * (1.0 - a - b)
            var = garch_variances(y, mean, omega, a, b)[:-1]
            ll = float(-0.5 * (LOG_2PI + np.log(var) + (y - mean) ** 2 / var).sum())
            if ll > best[0]:
                best = (ll, a, b)
    _, a, b = best
    return mean, sample_var * (1.0 - a - b), a, b


# --- one interface for the laboratory -------------------------------------------------------------


@dataclass
class ModelSpec:
    key: str
    label: str
    family: str  # REGIME or RISK
    params: dict[str, float] = field(default_factory=dict)


MODELS: tuple[ModelSpec, ...] = (
    ModelSpec("HMM2", "Regimes: HMM com 2 estados", "REGIME", {"states": 2}),
    ModelSpec("HMM3", "Regimes: HMM com 3 estados", "REGIME", {"states": 3}),
    ModelSpec("GMM2", "Regimes: mistura gaussiana com 2 componentes", "REGIME", {"components": 2}),
    ModelSpec("EWMA85", "Risco: EWMA com λ = 0,85", "RISK", {"decay": 0.85}),
    ModelSpec("EWMA94", "Risco: EWMA com λ = 0,94", "RISK", {"decay": 0.94}),
    ModelSpec("GARCH11", "Risco: GARCH(1,1)", "RISK", {}),
)


def forecast_logscores(
    y: np.ndarray, spec: ModelSpec | None, *, start: int, refit_every: int = 12
) -> np.ndarray:
    """Log density of y[t] forecast from y[:t], for t = start..T-1 (None: the reference)."""
    out = np.empty(y.size - start)
    fitted = None
    fitted_at = -(10**9)
    for i, t in enumerate(range(start, y.size)):
        train = y[:t]
        if spec is None:
            out[i] = normal_logpdf(float(y[t]), float(train.mean()), float(train.var(ddof=1)))
            continue
        if t - fitted_at >= refit_every or fitted is None:
            if spec.key.startswith("HMM"):
                fitted = fit_hmm(train, int(spec.params["states"]))
            elif spec.key.startswith("GMM"):
                fitted = fit_mixture(train, int(spec.params["components"]))
            elif spec.key.startswith("GARCH"):
                fitted = fit_garch(train)
            else:
                fitted = (float(train.mean()),)
            fitted_at = t
        if spec.key.startswith("HMM"):
            p: HmmParams = fitted  # type: ignore[assignment]
            filtered = hmm_filter(train, p)[-1]
            out[i] = mixture_logpdf(float(y[t]), filtered @ p.transition, p.means, p.variances)
        elif spec.key.startswith("GMM"):
            m: MixtureParams = fitted  # type: ignore[assignment]
            out[i] = mixture_logpdf(float(y[t]), m.weights, m.means, m.variances)
        elif spec.key.startswith("GARCH"):
            mean, omega, a, b = fitted  # type: ignore[misc]
            var = garch_variances(train, mean, omega, a, b)[-1]
            out[i] = normal_logpdf(float(y[t]), mean, var)
        else:
            decay = spec.params["decay"]
            mean = float(train.mean())
            var = float(train[:12].var(ddof=1)) if train.size > 12 else float(train.var())
            for r in train[12:]:
                var = decay * var + (1.0 - decay) * (r - mean) ** 2
            out[i] = normal_logpdf(float(y[t]), mean, var)
    return out
