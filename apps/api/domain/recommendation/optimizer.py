"""The full optimizer of the weights inside a class (Phase 45.8b; design 34, decisions 10.1.1-4).

It maximizes the same utility as the construction, U = expected return over the class - lambda x
annual volatility, but over every weight at once instead of adding one asset at a time:

- candidates: the best of the decision matrix by rank, at most `max_per_sector` per sector, twice
  K_max of them; the result keeps at most K_max assets above the minimum weight;
- constraints: weights add to 1, the sector and correlation-group caps (25% of the class, relaxed
  as in the construction when there are too few sectors), and the 12-month CVaR 95% no worse than
  that of the class's current holdings (Rockafellar and Uryasev's linear form), when there are
  holdings to compare;
- robustness (Michaud's resampling): each draw resamples the months of the history (the
  covariance and the 12-month scenarios) and perturbs each expected return by its uncertainty
  (1 - confidence); the weights are the average over the draws, and each asset says in how many
  draws it entered and the 90% range of its weight.

The optimizer does not decide alone: its weights become the class's target only when the
walk-forward test shows it beat the construction out of sample (decision 10.1.4); until then
it is a reference next to the construction.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import numpy as np
from scipy.optimize import minimize

from domain.recommendation.combination import ClassMatrix, MatrixRow
from domain.recommendation.construction import (
    ClassConstruction,
    _cap,
    _evaluate,
    _feasible_cap,
    correlation_groups,
    covariance,
)
from domain.recommendation.params import ConstructionParams

Month = tuple[int, int]

OK = "OK"
NO_CANDIDATES = "NO_CANDIDATES"
TESTED_CLASSES = frozenset({"ACOES"})  # where the walk-forward test runs
DEFAULT_VOLATILITY = 0.30  # a year, when an asset has no history
RIDGE = 1e-6


@dataclass(frozen=True)
class OptimizerParams:
    draws: int = 16
    scenarios: int = 200
    horizon_months: int = 12
    cvar_level: float = 0.95
    min_weight: float = 0.02
    history_months: int = 60
    seed: int = 4582


@dataclass(frozen=True)
class OptimizedAsset:
    ticker: str
    weight: float
    low: float  # 5th percentile of the weight over the draws
    high: float  # 95th percentile
    frequency: float  # share of the draws where it got at least the minimum weight
    construction_weight: float = 0.0


@dataclass(frozen=True)
class OptimizedClass:
    arca_class: str
    as_of: date
    status: str
    assets: list[OptimizedAsset] = field(default_factory=list)
    expected: float = 0.0
    risk: float = 0.0
    utility: float = 0.0
    construction_utility: float = 0.0
    cvar: float | None = None  # 12-month CVaR 95% of the optimized weights (a loss, positive)
    current_cvar: float | None = None
    construction_cvar: float | None = None
    cvar_bound: bool = False  # whether the CVaR constraint was applied
    draws: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def weights(self) -> dict[str, float]:
        return {a.ticker: a.weight for a in self.assets}

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["as_of"] = self.as_of.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OptimizedClass:
        payload = dict(data)
        payload["as_of"] = date.fromisoformat(payload["as_of"])
        payload["assets"] = [OptimizedAsset(**a) for a in payload.get("assets", [])]
        return cls(**payload)


def candidates(rows: Sequence[MatrixRow], params: ConstructionParams) -> list[MatrixRow]:
    """The best rows by rank, at most `max_per_sector` per sector, up to twice K_max."""
    out: list[MatrixRow] = []
    count: dict[str, int] = {}
    for r in sorted(rows, key=lambda r: r.rank):
        sector = r.sector or r.ticker
        if count.get(sector, 0) >= params.max_per_sector:
            continue
        out.append(r)
        count[sector] = count.get(sector, 0) + 1
        if len(out) >= 2 * params.k_max:
            break
    return out


def _history(
    returns: Mapping[str, Mapping[Month, float]], tickers: Sequence[str], months: int
) -> np.ndarray:
    """Months x tickers of demeaned monthly returns (0 where missing): the shocks to resample."""
    span = sorted({m for t in tickers for m in returns.get(t, {})})[-months:]
    data = np.array(
        [[returns.get(t, {}).get(m, np.nan) for t in tickers] for m in span], dtype=float
    ).reshape(len(span), len(tickers))
    if data.size:
        means = np.nanmean(np.where(np.isfinite(data), data, np.nan), axis=0)
        means = np.where(np.isfinite(means), means, 0.0)
        data = np.where(np.isfinite(data), data - means, 0.0)
    return data


def cvar(losses: np.ndarray, level: float) -> float:
    """Mean of the worst (1 - level) share of the losses."""
    if losses.size == 0:
        return 0.0
    tail = max(1, math.ceil((1.0 - level) * losses.size))
    return float(np.sort(losses)[-tail:].mean())


def _scenarios(
    shocks: np.ndarray, mu: np.ndarray, rng: np.random.Generator, count: int, horizon: int
) -> np.ndarray:
    """`count` 12-month returns: the expected return plus the sum of resampled monthly shocks."""
    if shocks.shape[0] == 0:
        return np.tile(mu, (count, 1))
    picks = rng.integers(0, shocks.shape[0], size=(count, horizon))
    return mu + shocks[picks].sum(axis=1)


def _covariance(shocks: np.ndarray, n: int) -> np.ndarray:
    if shocks.shape[0] < 3:
        return np.eye(n) * DEFAULT_VOLATILITY**2
    cov = np.atleast_2d(np.cov(shocks, rowvar=False, ddof=1)) * 12.0
    diag = np.diag(cov).copy()
    fill = float(np.mean(diag[diag > 0])) if (diag > 0).any() else DEFAULT_VOLATILITY**2
    for i in range(n):
        if cov[i, i] <= 0:
            cov[i, i] = fill
    return cov + np.eye(n) * RIDGE


def _caps(
    tickers: Sequence[str], labels: Mapping[str, str], cap: float
) -> list[tuple[np.ndarray, float]]:
    out = []
    for label in sorted({labels[t] for t in tickers}):
        mask = np.array([labels[t] == label for t in tickers], dtype=float)
        if mask.sum() > 1:
            out.append((mask, cap))
    return out


def solve(
    mu: np.ndarray,
    cov: np.ndarray,
    risk_aversion: float,
    caps: Sequence[tuple[np.ndarray, float]],
    upper: float,
    scenarios: np.ndarray | None = None,
    limit: float | None = None,
    level: float = 0.95,
) -> np.ndarray | None:
    """Weights that maximize mu.w - lambda sqrt(w'Cw) under the caps and, with `limit`, the CVaR
    of the scenarios at or below it. None when the solver finds no feasible point."""
    n = mu.size
    with_cvar = scenarios is not None and limit is not None
    s = scenarios.shape[0] if with_cvar else 0  # type: ignore[union-attr]
    scale = 1.0 / ((1.0 - level) * s) if s else 0.0

    def split(x: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
        return x[:n], (x[n] if with_cvar else 0.0), x[n + 1 :] if with_cvar else np.zeros(0)

    def objective(x: np.ndarray) -> float:
        w = x[:n]
        return -(float(mu @ w) - risk_aversion * math.sqrt(max(float(w @ cov @ w), 1e-12)))

    def gradient(x: np.ndarray) -> np.ndarray:
        w = x[:n]
        vol = math.sqrt(max(float(w @ cov @ w), 1e-12))
        g = np.zeros_like(x)
        g[:n] = -(mu - risk_aversion * (cov @ w) / vol)
        return g

    size = n + (1 + s if with_cvar else 0)
    constraints: list[dict[str, Any]] = [
        {
            "type": "eq",
            "fun": lambda x: float(x[:n].sum() - 1.0),
            "jac": lambda x: np.concatenate([np.ones(n), np.zeros(size - n)]),
        }
    ]
    for mask, cap in caps:
        constraints.append(
            {
                "type": "ineq",
                "fun": lambda x, m=mask, c=cap: float(c - m @ x[:n]),
                "jac": lambda x, m=mask: np.concatenate([-m, np.zeros(size - n)]),
            }
        )
    if with_cvar:
        r = scenarios  # type: ignore[assignment]
        constraints.append(
            {
                "type": "ineq",
                "fun": lambda x: float(limit - (split(x)[1] + scale * split(x)[2].sum())),  # type: ignore[operator]
                "jac": lambda x: np.concatenate([np.zeros(n), [-1.0], -scale * np.ones(s)]),
            }
        )
        jac_tail = np.hstack([r, np.ones((s, 1)), np.eye(s)])  # type: ignore[arg-type]
        constraints.append(
            {
                "type": "ineq",
                "fun": lambda x: split(x)[2] + split(x)[1] + r @ x[:n],  # type: ignore[operator]
                "jac": lambda x: jac_tail,
            }
        )
    w0 = np.full(n, 1.0 / n)
    x0 = w0
    bounds: list[tuple[float | None, float | None]] = [(0.0, upper)] * n
    if with_cvar:
        losses = -(r @ w0)  # type: ignore[operator]
        alpha = float(np.quantile(losses, level))
        x0 = np.concatenate([w0, [alpha], np.maximum(losses - alpha, 0.0)])
        bounds += [(None, None)] + [(0.0, None)] * s
    found = minimize(
        objective,
        x0,
        jac=gradient,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 300, "ftol": 1e-9},
    )
    if not found.success:
        return None
    w = np.clip(found.x[:n], 0.0, None)
    total = w.sum()
    return w / total if total > 0 else None


def _final(
    average: Mapping[str, float],
    sectors: Mapping[str, str],
    groups: Mapping[str, str],
    params: ConstructionParams,
    minimum: float,
) -> dict[str, float]:
    """Keep the K_max largest weights above the minimum, then the caps again."""
    kept = sorted(
        ((t, w) for t, w in average.items() if w >= minimum), key=lambda tw: (-tw[1], tw[0])
    )[: params.k_max]
    if not kept:
        kept = sorted(average.items(), key=lambda tw: (-tw[1], tw[0]))[:1]
    total = sum(w for _, w in kept) or 1.0
    weights = {t: w / total for t, w in kept}
    sector_cap = _feasible_cap(params.sector_cap, [sectors[t] for t in weights])
    group_cap = _feasible_cap(params.group_cap, [groups[t] for t in weights])
    asset_cap = _feasible_cap(params.asset_cap, list(weights))
    for _ in range(3):
        weights = _cap(weights, {t: t for t in weights}, asset_cap)
        weights = _cap(weights, {t: groups[t] for t in weights}, group_cap)
        weights = _cap(weights, {t: sectors[t] for t in weights}, sector_cap)
    norm = sum(weights.values()) or 1.0
    return {t: w / norm for t, w in weights.items()}


def optimize_class(
    matrix: ClassMatrix,
    returns: Mapping[str, Mapping[Month, float]],
    params: ConstructionParams,
    *,
    current: Mapping[str, float] | None = None,
    construction: ClassConstruction | None = None,
    options: OptimizerParams | None = None,
) -> OptimizedClass:
    """The class's optimized weights, resampled (see the module docstring).

    `current` holds the value of each asset the class holds today (for the CVaR limit);
    `construction` is the simple construction, measured on the same scenarios for comparison.
    """
    opts = options or OptimizerParams()
    rows = candidates(matrix.rows, params)
    if not rows:
        return OptimizedClass(matrix.arca_class, matrix.as_of, NO_CANDIDATES)
    tickers = [r.ticker for r in rows]
    held = {t: v for t, v in (current or {}).items() if v > 0 and t in returns}
    total_held = sum(held.values())
    extra = sorted(t for t in held if t not in tickers)
    every = [*tickers, *extra]
    n = len(tickers)
    sectors = {r.ticker: r.sector or r.ticker for r in rows}
    groups = correlation_groups(returns, tickers)
    sector_cap = _feasible_cap(params.sector_cap, [sectors[t] for t in tickers])
    group_cap = _feasible_cap(params.group_cap, [groups[t] for t in tickers])
    caps = [*_caps(tickers, sectors, sector_cap), *_caps(tickers, groups, group_cap)]
    upper = min(sector_cap, _feasible_cap(params.asset_cap, tickers))
    mu = np.array([r.expected for r in rows], dtype=float)
    mu_all = np.concatenate([mu, np.zeros(len(extra))])
    spread = np.array([(1.0 - r.confidence) * max(abs(r.expected), 0.01) for r in rows])
    shocks = _history(returns, every, opts.history_months)
    w_now = np.array([held.get(t, 0.0) / total_held for t in every]) if total_held > 0 else None
    notes: list[str] = []
    if w_now is None:
        notes.append("Sem posições na classe: sem limite de CVaR (nada a comparar).")
    if shocks.shape[0] < 12:
        notes.append(f"Só {shocks.shape[0]} meses de histórico: risco e cenários pouco firmes.")

    found: list[np.ndarray] = []
    relaxed = 0
    for b in range(opts.draws):
        rng = np.random.default_rng(opts.seed + b)
        sample = (
            shocks[rng.integers(0, shocks.shape[0], shocks.shape[0])] if shocks.size else shocks
        )
        mu_b = mu + rng.normal(0.0, spread)
        cov_b = _covariance(sample[:, :n] if sample.size else sample.reshape(0, n), n)
        limit = None
        scen = None
        if w_now is not None:
            scen_all = _scenarios(
                sample, np.concatenate([mu_b, mu_all[n:]]), rng, opts.scenarios, opts.horizon_months
            )
            limit = cvar(-(scen_all @ w_now), opts.cvar_level)
            scen = scen_all[:, :n]
        w = solve(mu_b, cov_b, params.risk_aversion, caps, upper, scen, limit, opts.cvar_level)
        if w is None and limit is not None:
            relaxed += 1
            w = solve(mu_b, cov_b, params.risk_aversion, caps, upper)
        if w is not None:
            found.append(w)
    if relaxed:
        notes.append(
            f"Em {relaxed} de {opts.draws} sorteios nenhuma carteira dos candidatos tinha CVaR tão "
            "baixo quanto o da carteira atual; nesses o limite foi tirado."
        )
    if not found:
        return OptimizedClass(
            matrix.arca_class,
            matrix.as_of,
            NO_CANDIDATES,
            notes=[*notes, "O otimizador não convergiu."],
        )
    stack = np.vstack(found)
    average = dict(zip(tickers, stack.mean(axis=0).tolist(), strict=True))
    weights = _final(average, sectors, groups, params, opts.min_weight)

    # Measured on the full history, with the expected returns as they are (no draw).
    full_cov = covariance(returns, tickers)
    index = {t: i for i, t in enumerate(tickers)}
    by_ticker = {r.ticker: r for r in rows}
    chosen = [by_ticker[t] for t in weights]
    expected, risk, utility = _evaluate(chosen, weights, full_cov, index, params.risk_aversion)
    built = {s.ticker: s.weight for s in construction.selected} if construction else {}
    built_utility = 0.0
    if built and all(t in index for t in built):
        _e, _r, built_utility = _evaluate(
            [by_ticker[t] for t in built], built, full_cov, index, params.risk_aversion
        )
    rng = np.random.default_rng(opts.seed - 1)
    check = _scenarios(shocks, mu_all, rng, max(opts.scenarios, 1000), opts.horizon_months)

    def measure(w: Mapping[str, float]) -> float | None:
        if not w or any(t not in every for t in w):
            return None
        vector = np.array([w.get(t, 0.0) for t in every])
        return round(cvar(-(check @ vector), opts.cvar_level), 6)

    in_draws = stack >= opts.min_weight
    assets = [
        OptimizedAsset(
            ticker=t,
            weight=round(weights[t], 6),
            low=round(float(np.percentile(stack[:, index[t]], 5)), 6),
            high=round(float(np.percentile(stack[:, index[t]], 95)), 6),
            frequency=round(float(in_draws[:, index[t]].mean()), 4),
            construction_weight=round(built.get(t, 0.0), 6),
        )
        for t in sorted(weights, key=lambda t: (-weights[t], t))
    ]
    unstable = [a.ticker for a in assets if a.frequency < 0.5]
    if unstable:
        notes.append(
            "Instáveis (entram em menos da metade dos sorteios): " + ", ".join(unstable) + "."
        )
    return OptimizedClass(
        arca_class=matrix.arca_class,
        as_of=matrix.as_of,
        status=OK,
        assets=assets,
        expected=round(expected, 6),
        risk=round(risk, 6),
        utility=round(utility, 6),
        construction_utility=round(built_utility, 6),
        cvar=measure(weights),
        current_cvar=measure({t: held[t] / total_held for t in held}) if total_held else None,
        construction_cvar=measure(built) if built else None,
        cvar_bound=w_now is not None,
        draws=len(found),
        notes=notes,
    )


def optimizer_applies(arca_class: str, passed: bool) -> bool:
    """The walk-forward test only covers the classes with a point-in-time panel: passing it says
    nothing about the others, which keep the construction."""
    return passed and arca_class in TESTED_CLASSES


def optimized_of(construction: ClassConstruction) -> OptimizedClass | None:
    """The optimizer's result stored with a construction (None before Phase 45.8b)."""
    data = construction.optimized
    return OptimizedClass.from_dict(data) if data else None


def target_weights(construction: ClassConstruction, optimizer_passed: bool) -> dict[str, float]:
    """The class's target: the optimizer's weights once it passed its gate, else the
    construction's (decision 10.1.4)."""
    found = optimized_of(construction)
    applies = optimizer_applies(construction.arca_class, optimizer_passed)
    if applies and found is not None and found.status == OK and found.assets:
        return found.weights
    return {s.ticker: s.weight for s in construction.selected}


def optimizer_passed(payload: Mapping[str, Any] | None) -> bool:
    """Whether the stored backtest says the optimizer beat the construction."""
    return bool(payload and (payload.get("backtest") or {}).get("optimizer_passed"))
