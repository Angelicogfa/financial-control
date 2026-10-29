"""Statistical validation against overfitting (Phase 33.8; design 7.2, 6.5 and risk R3).

- Purged walk-forward splits (López de Prado, 2018): train only on the past; drop from the
  training set the observations whose label window overlaps the test window, plus an
  embargo after it, so overlapping labels cannot leak the test period.
- Deflated Sharpe ratio (Bailey & López de Prado, 2014): the probability that the best
  Sharpe ratio of N trials beats the maximum expected from N trials of pure noise, with the
  skewness and kurtosis of its returns.
- Probability of backtest overfitting by combinatorially symmetric cross-validation (Bailey,
  Borwein, López de Prado & Zhu): how often the configuration that is best in-sample ranks
  below the median out-of-sample.
- Bayesian gate (design 6.5): P(mean difference > 0) between a candidate and its reference
  by the Bayesian bootstrap (Dirichlet weights); it passes at 95% or more.

On pure noise these give the null result the design asks for: PBO near 50% and a deflated
Sharpe that is not significant.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

EULER_GAMMA = 0.5772156649015329
SIGNIFICANCE = 0.95
GATE_PROBABILITY = 0.95
CSCV_BLOCKS = 10
GATE_DRAWS = 4000


# --- normal distribution (no scipy) --------------------------------------------------------------


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """Inverse of the standard normal CDF by bisection (accurate to 1e-10)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    low, high = -40.0, 40.0
    for _ in range(200):
        mid = (low + high) / 2.0
        if norm_cdf(mid) < p:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


# --- walk-forward --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Split:
    train: np.ndarray
    test: np.ndarray


def purged_walk_forward(
    n: int,
    *,
    min_train: int,
    test_size: int,
    label_horizon: int = 1,
    embargo: int = 0,
) -> list[Split]:
    """Expanding-window splits; a label at t covers [t, t + label_horizon - 1].

    Training observations whose label window reaches the test window are purged, and a gap
    of `embargo` observations separates consecutive test windows (their serial correlation
    then does not tie one test window to the next).
    """
    splits: list[Split] = []
    start = min_train
    while start + test_size <= n:
        test = np.arange(start, start + test_size)
        train_end = start - (label_horizon - 1)  # labels ending before the test starts
        train = np.arange(0, max(train_end, 0))
        splits.append(Split(train=train, test=test))
        start += test_size + embargo
    return splits


# --- Sharpe and deflated Sharpe -----------------------------------------------------------------


def sharpe(returns: Sequence[float] | np.ndarray) -> float:
    """Per-period Sharpe ratio of excess returns (0 when flat)."""
    x = np.asarray(returns, dtype=float)
    if x.size < 2:
        return 0.0
    sd = float(x.std(ddof=1))
    return float(x.mean() / sd) if sd > 0 else 0.0


def expected_max_sharpe(n_trials: int, var_sharpe: float) -> float:
    """E[max SR] of N independent trials with zero true Sharpe and variance `var_sharpe`."""
    if n_trials <= 1:
        return 0.0
    sd = math.sqrt(max(var_sharpe, 0.0))
    return sd * (
        (1.0 - EULER_GAMMA) * norm_ppf(1.0 - 1.0 / n_trials)
        + EULER_GAMMA * norm_ppf(1.0 - 1.0 / (n_trials * math.e))
    )


def probabilistic_sharpe(
    observed: float, benchmark: float, n_obs: int, skew: float, kurtosis: float
) -> float:
    """P(true SR > benchmark) given the observed per-period SR (Bailey & López de Prado)."""
    if n_obs < 2:
        return 0.5
    denom = 1.0 - skew * observed + (kurtosis - 1.0) / 4.0 * observed**2
    if denom <= 0:
        return 0.5
    return norm_cdf((observed - benchmark) * math.sqrt(n_obs - 1) / math.sqrt(denom))


def moments(returns: np.ndarray) -> tuple[float, float]:
    """Skewness and (non-excess) kurtosis."""
    x = returns - returns.mean()
    sd = float(x.std())
    if sd == 0:
        return 0.0, 3.0
    return float((x**3).mean() / sd**3), float((x**4).mean() / sd**4)


@dataclass(frozen=True)
class DeflatedSharpe:
    sharpe: float  # per period, of the selected trial
    expected_max: float  # per period, of N noise trials
    probability: float  # P(true SR > expected max)
    trials: int
    observations: int

    @property
    def significant(self) -> bool:
        return self.probability >= SIGNIFICANCE


def deflated_sharpe(
    selected: np.ndarray, all_trial_sharpes: Sequence[float], *, n_trials: int | None = None
) -> DeflatedSharpe:
    """Deflate the Sharpe of the selected trial by the number of trials behind it.

    `n_trials` is every configuration ever tried (risk R3), which may exceed the ones whose
    Sharpe is known; the variance of the Sharpe ratios comes from the known ones.
    """
    trials = n_trials or len(all_trial_sharpes)
    sr = sharpe(selected)
    var = float(np.var(all_trial_sharpes, ddof=1)) if len(all_trial_sharpes) > 1 else 0.0
    sr0 = expected_max_sharpe(trials, var)
    skew, kurt = moments(selected)
    return DeflatedSharpe(
        sharpe=round(sr, 6),
        expected_max=round(sr0, 6),
        probability=round(probabilistic_sharpe(sr, sr0, selected.size, skew, kurt), 4),
        trials=trials,
        observations=int(selected.size),
    )


# --- PBO by CSCV ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class OverfittingProbability:
    pbo: float
    combinations: int
    blocks: int
    logits: list[float] = field(default_factory=list, repr=False)


def pbo_cscv(performance: np.ndarray, *, blocks: int = CSCV_BLOCKS) -> OverfittingProbability:
    """PBO of a (T periods × N configurations) matrix of returns.

    The T rows are cut into `blocks` contiguous groups; every half of the groups is an
    in-sample set and the other half its out-of-sample set. For each split the in-sample
    best (by Sharpe) gets its out-of-sample relative rank ω; PBO = P(logit(ω) <= 0).
    """
    t, n = performance.shape
    if n < 2:
        raise ValueError("PBO needs at least two configurations")
    blocks = min(blocks - blocks % 2, t - t % 2)
    if blocks < 2:
        raise ValueError("PBO needs at least two blocks of observations")
    edges = np.linspace(0, t, blocks + 1).astype(int)
    sums = np.array([performance[a:b].sum(axis=0) for a, b in zip(edges, edges[1:], strict=False)])
    sumsq = np.array(
        [(performance[a:b] ** 2).sum(axis=0) for a, b in zip(edges, edges[1:], strict=False)]
    )
    counts = np.diff(edges)

    def sharpe_of(groups: Sequence[int]) -> np.ndarray:
        k = counts[list(groups)].sum()
        s = sums[list(groups)].sum(axis=0)
        q = sumsq[list(groups)].sum(axis=0)
        mean = s / k
        var = np.maximum(q / k - mean**2, 1e-18) * k / max(k - 1, 1)
        return mean / np.sqrt(var)

    logits: list[float] = []
    every = set(range(blocks))
    for chosen in itertools.combinations(range(blocks), blocks // 2):
        is_sr = sharpe_of(chosen)
        oos_sr = sharpe_of(sorted(every - set(chosen)))
        best = int(np.argmax(is_sr))
        rank = int((oos_sr < oos_sr[best]).sum()) + 1  # 1 = worst out of sample
        omega = rank / (n + 1)
        logits.append(math.log(omega / (1.0 - omega)))
    arr = np.array(logits)
    return OverfittingProbability(
        pbo=round(float((arr <= 0).mean()), 4),
        combinations=len(logits),
        blocks=blocks,
        logits=[round(v, 4) for v in logits],
    )


# --- Bayesian gate -------------------------------------------------------------------------------


@dataclass(frozen=True)
class BayesianGate:
    probability: float  # P(mean difference > 0)
    mean_difference: float
    observations: int

    @property
    def passed(self) -> bool:
        return self.probability >= GATE_PROBABILITY


def bayesian_gate(
    candidate: np.ndarray, reference: np.ndarray, *, seed: int, draws: int = GATE_DRAWS
) -> BayesianGate:
    """Bayesian bootstrap of the mean paired difference (per period) candidate − reference."""
    diff = np.asarray(candidate, dtype=float) - np.asarray(reference, dtype=float)
    if diff.size < 2:
        return BayesianGate(0.5, float(diff.mean()) if diff.size else 0.0, int(diff.size))
    rng = np.random.default_rng(seed)
    weights = rng.dirichlet(np.ones(diff.size), size=draws)
    means = weights @ diff
    return BayesianGate(
        probability=round(float((means > 0).mean()), 4),
        mean_difference=round(float(diff.mean()), 6),
        observations=int(diff.size),
    )


# --- a set of configurations ---------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationReport:
    """Verdict on the best of several configurations (rule variants, models)."""

    best: str
    best_sharpe_annual: float
    deflated: DeflatedSharpe
    overfitting: OverfittingProbability | None
    gate: BayesianGate | None
    passed: bool
    verdict: str
    notes: list[str] = field(default_factory=list)


def validate_configurations(
    returns: Mapping[str, np.ndarray],
    *,
    reference: np.ndarray | None = None,
    n_trials: int | None = None,
    periods_per_year: int = 12,
    seed: int = 0,
) -> ValidationReport:
    """Deflated Sharpe of the best, PBO of the set and the gate of the best against a reference.

    All series must be aligned (same periods). Passing needs the three: a significant deflated
    Sharpe, PBO below 50% and P(better than the reference) of 95% or more.
    """
    names = list(returns)
    matrix = np.column_stack([returns[k] for k in names])
    sharpes = [sharpe(matrix[:, j]) for j in range(len(names))]
    best_j = int(np.argmax(sharpes))
    best = names[best_j]
    deflated = deflated_sharpe(matrix[:, best_j], sharpes, n_trials=n_trials)
    notes: list[str] = []
    overfitting = None
    if len(names) >= 2 and matrix.shape[0] >= 4:
        overfitting = pbo_cscv(matrix)
    else:
        notes.append("Com uma configuração só, não há como medir o PBO.")
    gate = bayesian_gate(matrix[:, best_j], reference, seed=seed) if reference is not None else None
    passed = bool(
        deflated.significant
        and (overfitting is None or overfitting.pbo < 0.5)
        and (gate is None or gate.passed)
    )
    if passed:
        verdict = (
            f"{best} passou: o Sharpe se mantém depois de descontar {deflated.trials} tentativas, "
            "a escolha não parece ajuste ao ruído e supera a referência com 95% ou mais."
        )
    else:
        reasons = []
        if not deflated.significant:
            reasons.append(
                f"o Sharpe de {best} não supera o máximo esperado do acaso em "
                f"{deflated.trials} tentativas"
            )
        if overfitting is not None and overfitting.pbo >= 0.5:
            reasons.append(f"a probabilidade de ajuste ao ruído é de {overfitting.pbo:.0%}")
        if gate is not None and not gate.passed:
            reasons.append(f"a chance de superar a referência é de só {gate.probability:.0%}")
        verdict = (
            "Sem evidência de que a melhor configuração seja melhor de verdade: "
            + "; ".join(reasons)
            + "."
        )
    return ValidationReport(
        best=best,
        best_sharpe_annual=round(sharpes[best_j] * math.sqrt(periods_per_year), 4),
        deflated=deflated,
        overfitting=overfitting,
        gate=gate,
        passed=passed,
        verdict=verdict,
        notes=notes,
    )
