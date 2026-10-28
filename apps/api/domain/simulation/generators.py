"""Scenario generators of the monthly class returns in excess of the CDI (Phase 33.6).

- BOOTSTRAP: stationary block bootstrap of the history (Politis & Romano), equal weights.
- BAYESIAN_BOOTSTRAP: the same blocks with Dirichlet(1, ..., 1) weights on the months, one
  draw per path (Rubin, 1981): the uncertainty of the generator itself by resampling.
- BAYESIAN_NORMAL: each path draws (μ, Σ) from the normal-inverse-Wishart posterior, then
  independent normal monthly log excess returns.

The projection mixes them with the stacking weights of the weekly calibration (design 6.4).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

import numpy as np

from domain.shared.enums import ArcaClass
from domain.simulation.bayes import NiwPosterior, niw_posterior, normal_log_paths
from domain.simulation.scenarios import (
    CLASS_ORDER,
    ClassSample,
    stationary_bootstrap_indices,
)


class Generator(StrEnum):
    BOOTSTRAP = "BOOTSTRAP"
    BAYESIAN_BOOTSTRAP = "BAYESIAN_BOOTSTRAP"
    BAYESIAN_NORMAL = "BAYESIAN_NORMAL"


GENERATOR_LABELS: dict[str, str] = {
    Generator.BOOTSTRAP: "Bootstrap em blocos",
    Generator.BAYESIAN_BOOTSTRAP: "Bootstrap bayesiano",
    Generator.BAYESIAN_NORMAL: "Normal bayesiana",
    "STACKED": "Combinação (stacking)",
}
EQUAL_WEIGHTS: dict[str, float] = {g.value: 1.0 / len(Generator) for g in Generator}


def risky_columns(sample: ClassSample) -> list[int]:
    """Columns of CLASS_ORDER with a market proxy in the sample (Caixa has no excess)."""
    return [CLASS_ORDER.index(c) for c in sample.classes if c != ArcaClass.CAIXA]


def sample_posterior(sample: ClassSample) -> NiwPosterior | None:
    """The posterior of the sample's risky classes (None when only Caixa is held)."""
    cols = risky_columns(sample)
    if not cols:
        return None
    x = np.log1p(sample.excess[:, cols])
    return niw_posterior(x, [CLASS_ORDER[c] for c in cols])


def bayesian_bootstrap_indices(
    n: int, horizon: int, paths: int, mean_block: float, rng: np.random.Generator
) -> np.ndarray:
    """Stationary blocks whose starting months follow one Dirichlet weight vector per path."""
    weights = rng.dirichlet(np.ones(n), size=paths)
    cum = np.cumsum(weights, axis=1)
    starts = np.empty((paths, horizon), dtype=np.int64)
    u = rng.random((paths, horizon))
    for p in range(paths):
        starts[p] = np.minimum(np.searchsorted(cum[p], u[p]), n - 1)
    p_restart = 1.0 / mean_block
    restart = rng.random((paths, horizon)) < p_restart
    idx = np.empty((paths, horizon), dtype=np.int64)
    idx[:, 0] = starts[:, 0]
    for t in range(1, horizon):
        idx[:, t] = np.where(restart[:, t], starts[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def draw_excess(
    sample: ClassSample,
    generator: str,
    paths: int,
    horizon: int,
    *,
    mean_block: float,
    rng: np.random.Generator,
    posterior: NiwPosterior | None = None,
) -> np.ndarray:
    """(paths, horizon, K) monthly simple excess over the CDI, columns in CLASS_ORDER."""
    if generator == Generator.BOOTSTRAP:
        return sample.excess[
            stationary_bootstrap_indices(sample.size, horizon, paths, mean_block, rng)
        ]
    if generator == Generator.BAYESIAN_BOOTSTRAP:
        return sample.excess[
            bayesian_bootstrap_indices(sample.size, horizon, paths, mean_block, rng)
        ]
    if generator == Generator.BAYESIAN_NORMAL:
        out = np.zeros((paths, horizon, len(CLASS_ORDER)))
        post = posterior if posterior is not None else sample_posterior(sample)
        if post is not None:
            cols = [CLASS_ORDER.index(c) for c in post.classes]
            out[:, :, cols] = np.expm1(normal_log_paths(post, paths, horizon, rng))
        return out
    raise ValueError(f"unknown generator {generator!r}")


def mixture_counts(weights: Mapping[str, float], paths: int) -> dict[str, int]:
    """Paths per generator in proportion to the weights (largest remainders, total = paths)."""
    keys = [k for k, w in weights.items() if w > 0]
    total = sum(weights[k] for k in keys)
    exact = {k: weights[k] / total * paths for k in keys}
    counts = {k: int(v) for k, v in exact.items()}
    for k in sorted(keys, key=lambda k: exact[k] - counts[k], reverse=True)[
        : paths - sum(counts.values())
    ]:
        counts[k] += 1
    return {k: v for k, v in counts.items() if v > 0}


def draw_mixture(
    sample: ClassSample,
    weights: Mapping[str, float],
    paths: int,
    horizon: int,
    *,
    mean_block: float,
    seed: int,
    posterior: NiwPosterior | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Excess paths of the mixture and the generator of each path (labels array)."""
    counts = mixture_counts(weights, paths)
    blocks, labels = [], []
    for i, generator in enumerate(Generator):
        n = counts.get(generator.value, 0)
        if n == 0:
            continue
        # One independent stream per generator: the same seed gives the same paths.
        rng = np.random.default_rng([seed, i])
        blocks.append(
            draw_excess(
                sample, generator, n, horizon, mean_block=mean_block, rng=rng, posterior=posterior
            )
        )
        labels.extend([generator.value] * n)
    return np.concatenate(blocks, axis=0), np.array(labels)
