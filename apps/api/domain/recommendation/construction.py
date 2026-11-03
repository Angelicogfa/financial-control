"""Construction of the weights inside each class (Phase 45.4, design N6; decisions 10.6, 10.9 and
10.10).

From the decision matrix (45.3), the assets enter one by one:

1. Sector rule: the next asset comes from a sector not yet covered; one of a covered sector only
   competes when its score beats the best of a new sector by more than the margin (0.5 standard
   deviation of the class's scores), and never past the maximum per sector. Among the assets the
   rule allows, the one that raises the utility most enters (so a diversifying asset can win
   over a slightly higher score that moves with the ones already chosen).
2. Weights of a set: proportional to the score, then capped per sector and per correlation group
   (25% of the class); when the set has too few sectors for the cap, the cap is relaxed to the
   smallest feasible one and the note says so.
3. Dynamic K: the utility of the set is U = expected return over the class - lambda x risk, the
   risk being the annual volatility of the weighted monthly returns (covariances measured on the
   stored history). Assets enter while the best next one raises U, at least K_min and at most
   K_max. The curve (K, expected, risk, U) keeps every step and the refused one.

Correlation groups join the assets whose monthly returns moved together (correlation at or above
0.7 over 36 months, single linkage): sectors with different labels can be one group.

Nothing here buys anything: the weights are the class's target, which the contribution pulls
toward the current weights by the confidence (45.4 shows it next to the current contribution;
the switch is 45.6).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import numpy as np

from domain.recommendation.combination import ClassMatrix, MatrixRow
from domain.recommendation.params import ConstructionParams

Month = tuple[int, int]

WITH_CERRADO = "WITH_CERRADO"
WITHOUT_CERRADO = "WITHOUT_CERRADO"

GROUP_CORRELATION = 0.7
GROUP_MONTHS = 36
MIN_OVERLAP_MONTHS = 12


@dataclass(frozen=True)
class CurvePoint:
    k: int
    added: str
    expected: float  # weighted expected return over the class, a year
    risk: float  # annual volatility of the set
    utility: float


@dataclass(frozen=True)
class SelectedAsset:
    ticker: str
    sector: str
    group: str
    weight: float  # target inside the class, before the pull toward the current weights
    score: float
    expected: float
    confidence: float
    reason: str


@dataclass(frozen=True)
class SkippedAsset:
    ticker: str
    reason: str


@dataclass(frozen=True)
class ClassConstruction:
    arca_class: str
    as_of: date
    k: int
    stop_reason: str
    confidence: float  # weighted confidence of the selected assets
    selected: list[SelectedAsset]
    skipped: list[SkippedAsset]
    curve: list[CurvePoint]
    notes: list[str] = field(default_factory=list)
    # The full optimizer's result for the same class (Phase 45.8b), as stored.
    optimized: dict[str, Any] | None = None
    # The construction's weights with and without the Cerrado lens, for the scoreboard.
    cerrado_variants: dict[str, dict[str, float]] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["as_of"] = self.as_of.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ClassConstruction:
        payload = dict(data)
        payload["as_of"] = date.fromisoformat(payload["as_of"])
        payload["selected"] = [SelectedAsset(**s) for s in payload["selected"]]
        payload["skipped"] = [SkippedAsset(**s) for s in payload["skipped"]]
        payload["curve"] = [CurvePoint(**c) for c in payload["curve"]]
        return cls(**payload)


# --- correlations and groups -------------------------------------------------------------------


def _aligned(returns: Mapping[str, Mapping[Month, float]], tickers: Sequence[str]) -> np.ndarray:
    """Months x tickers matrix of the last GROUP_MONTHS months (NaN where missing)."""
    months = sorted({m for t in tickers for m in returns.get(t, {})})[-GROUP_MONTHS:]
    return np.array(
        [[returns.get(t, {}).get(m, np.nan) for t in tickers] for m in months], dtype=float
    ).reshape(len(months), len(tickers))


def covariance(returns: Mapping[str, Mapping[Month, float]], tickers: Sequence[str]) -> np.ndarray:
    """Annual covariance from pairwise complete months; a pair with too few months gets 0 and a
    missing variance gets the average of the others."""
    n = len(tickers)
    data = _aligned(returns, tickers)
    cov = np.zeros((n, n))
    for i in range(n):
        for j in range(i, n):
            ok = np.isfinite(data[:, i]) & np.isfinite(data[:, j]) if data.size else np.array([])
            if ok.sum() >= MIN_OVERLAP_MONTHS:
                c = float(np.cov(data[ok, i], data[ok, j], ddof=1)[0, 1]) * 12.0
                cov[i, j] = cov[j, i] = c
    known = [cov[i, i] for i in range(n) if cov[i, i] > 0]
    fill = float(np.mean(known)) if known else 0.09  # 30% a year when nothing is known
    for i in range(n):
        if cov[i, i] <= 0:
            cov[i, i] = fill
    return cov


def correlation_groups(
    returns: Mapping[str, Mapping[Month, float]],
    tickers: Sequence[str],
    threshold: float = GROUP_CORRELATION,
) -> dict[str, str]:
    """Ticker -> group (named by its first member): assets that moved together, single linkage."""
    parent = {t: t for t in tickers}

    def root(t: str) -> str:
        while parent[t] != t:
            parent[t] = parent[parent[t]]
            t = parent[t]
        return t

    data = _aligned(returns, tickers)
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            ok = np.isfinite(data[:, i]) & np.isfinite(data[:, j]) if data.size else np.array([])
            if ok.sum() < MIN_OVERLAP_MONTHS:
                continue
            a, b = data[ok, i], data[ok, j]
            if np.std(a) == 0 or np.std(b) == 0:
                continue
            if float(np.corrcoef(a, b)[0, 1]) >= threshold:
                ra, rb = root(tickers[i]), root(tickers[j])
                if ra != rb:
                    first, second = sorted((ra, rb), key=tickers.index)
                    parent[second] = first
    return {t: root(t) for t in tickers}


# --- weights -----------------------------------------------------------------------------------


def _cap(weights: dict[str, float], groups: Mapping[str, str], cap: float) -> dict[str, float]:
    """Cap the total weight of each group, giving the excess to the uncapped groups."""
    out = dict(weights)
    for _ in range(len(out) + 1):
        totals: dict[str, float] = {}
        for t, w in out.items():
            totals[groups[t]] = totals.get(groups[t], 0.0) + w
        over = {g for g, w in totals.items() if w > cap + 1e-9}
        if not over:
            return out
        excess = 0.0
        for t in out:
            g = groups[t]
            if g in over:
                scaled = out[t] * cap / totals[g]
                excess += out[t] - scaled
                out[t] = scaled
        free = [t for t in out if totals[groups[t]] < cap - 1e-9]
        base = sum(out[t] for t in free)
        if not free or base <= 0:
            return out
        for t in free:
            out[t] += excess * out[t] / base
    return out


def _feasible_cap(cap: float, labels: Sequence[str]) -> float:
    return max(cap, 1.0 / max(len(set(labels)), 1))


def set_weights(
    rows: Sequence[MatrixRow],
    sectors: Mapping[str, str],
    groups: Mapping[str, str],
    params: ConstructionParams,
) -> tuple[dict[str, float], list[str]]:
    """Weights proportional to the score, capped per sector and per group."""
    total = sum(r.score for r in rows) or 1.0
    weights = {r.ticker: r.score / total for r in rows}
    notes = []
    tickers = [r.ticker for r in rows]
    sector_cap = _feasible_cap(params.sector_cap, [sectors[t] for t in tickers])
    group_cap = _feasible_cap(params.group_cap, [groups[t] for t in tickers])
    asset_cap = _feasible_cap(params.asset_cap, tickers)
    if asset_cap > params.asset_cap:
        notes.append(
            f"Poucos ativos para o teto de {params.asset_cap:.0%} da classe por ativo: "
            f"teto usado de {asset_cap:.0%}."
        )
    if sector_cap > params.sector_cap:
        notes.append(
            f"Poucos setores para o teto de {params.sector_cap:.0%}: "
            f"teto usado de {sector_cap:.0%}."
        )
    if group_cap > params.group_cap:
        notes.append(
            f"Poucos grupos para o teto de {params.group_cap:.0%}: teto usado de {group_cap:.0%}."
        )
    # The two caps interact; a few rounds settle them, the sector's last: when both cannot hold
    # together, the sector cap (the decision 10.9) prevails and the note says so.
    for _ in range(3):
        weights = _cap(weights, {t: t for t in weights}, asset_cap)
        weights = _cap(weights, {t: groups[t] for t in weights}, group_cap)
        weights = _cap(weights, {t: sectors[t] for t in weights}, sector_cap)
    norm = sum(weights.values()) or 1.0
    weights = {t: w / norm for t, w in weights.items()}
    by_group: dict[str, float] = {}
    for t, w in weights.items():
        by_group[groups[t]] = by_group.get(groups[t], 0.0) + w
    if max(by_group.values(), default=0.0) > group_cap + 1e-6:
        notes.append(
            "O teto por grupo não coube junto com o teto por setor; o de setor prevaleceu."
        )
    return weights, notes


def _evaluate(
    rows: Sequence[MatrixRow],
    weights: Mapping[str, float],
    cov: np.ndarray,
    index: Mapping[str, int],
    risk_aversion: float,
) -> tuple[float, float, float]:
    w = np.array([weights[r.ticker] for r in rows])
    idx = [index[r.ticker] for r in rows]
    expected = float(sum(weights[r.ticker] * r.expected for r in rows))
    risk = float(np.sqrt(max(w @ cov[np.ix_(idx, idx)] @ w, 0.0)))
    return expected, risk, expected - risk_aversion * risk


# --- the selection and the dynamic K -----------------------------------------------------------


def _decimal(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def allowed_now(
    remaining: Sequence[MatrixRow],
    sectors: Mapping[str, str],
    count: Mapping[str, int],
    margin: float,
) -> list[MatrixRow]:
    """Who may enter next: a sector not yet covered, or a covered one whose score beats the best
    of a new sector by more than the margin (decision 10.9); with no new sector left, anyone."""
    new = [r for r in remaining if count.get(sectors[r.ticker], 0) == 0]
    if not new:
        return list(remaining)
    best_new = max(r.score for r in new)
    return [
        r for r in remaining if count.get(sectors[r.ticker], 0) == 0 or r.score - best_new > margin
    ]


def build_class(
    matrix: ClassMatrix,
    returns: Mapping[str, Mapping[Month, float]],
    params: ConstructionParams,
) -> ClassConstruction:
    """The class's target weights with the dynamic K.

    At each step, among the assets the sector rule allows, the one that raises the utility most
    enters; the selection stops at the first step (from K_min on) where none raises it, or at
    K_max. The curve keeps every step and the one that was refused.
    """
    rows = list(matrix.rows)
    if not rows:
        return ClassConstruction(
            matrix.arca_class, matrix.as_of, 0, "Nenhum ativo apto nesta classe.", 0.0, [], [], []
        )
    sectors = {r.ticker: r.sector or r.ticker for r in rows}
    tickers = [r.ticker for r in rows]
    groups = correlation_groups(returns, tickers)
    cov = covariance(returns, tickers)
    index = {t: i for i, t in enumerate(tickers)}
    scores = [r.score for r in rows]
    margin = params.sector_margin_sd * (float(np.std(scores)) if len(scores) > 1 else 0.0)

    remaining = sorted(rows, key=lambda r: r.rank)
    chosen: list[MatrixRow] = []
    count: dict[str, int] = {}
    curve: list[CurvePoint] = []
    reasons: dict[str, str] = {}
    skipped: list[SkippedAsset] = []
    weights: dict[str, float] = {}
    notes: list[str] = []
    utility = -np.inf
    stop = ""
    while remaining:
        full = [r for r in remaining if count.get(sectors[r.ticker], 0) >= params.max_per_sector]
        skipped += [
            SkippedAsset(
                r.ticker,
                f"O setor {sectors[r.ticker]} já tem {params.max_per_sector} ativos escolhidos.",
            )
            for r in full
        ]
        remaining = [r for r in remaining if r not in full]
        if not remaining:
            break
        if len(chosen) >= params.k_max:
            stop = f"Parou no máximo de {params.k_max} ativos."
            break
        trials = []
        for r in allowed_now(remaining, sectors, count, margin):
            w, n = set_weights([*chosen, r], sectors, groups, params)
            e, risk, u = _evaluate([*chosen, r], w, cov, index, params.risk_aversion)
            trials.append((u, -r.score, r.rank, r, w, n, e, risk))
        trials.sort(key=lambda t: (-t[0], t[1], t[2]))
        u, _s, _rank, pick, w, n, e, risk = trials[0]
        point = CurvePoint(len(chosen) + 1, pick.ticker, round(e, 6), round(risk, 6), round(u, 6))
        if len(chosen) >= params.k_min and u <= utility:
            curve.append(point)
            stop = (
                f"Parou em {len(chosen)}: o melhor próximo ({pick.ticker}) não reduziria o risco "
                "o bastante para compensar a nota menor."
            )
            break
        new_sector = count.get(sectors[pick.ticker], 0) == 0
        reasons[pick.ticker] = (
            f"Setor novo ({sectors[pick.ticker]}); entre os permitidos, o que mais aumentou a "
            f"utilidade (nota {_decimal(pick.score)})."
            if new_sector
            else f"Setor já coberto, mas a nota {_decimal(pick.score)} supera a do melhor setor "
            "novo por mais que a margem."
        )
        chosen.append(pick)
        count[sectors[pick.ticker]] = count.get(sectors[pick.ticker], 0) + 1
        remaining = [r for r in remaining if r is not pick]
        curve.append(point)
        weights, notes, utility = w, n, u
    if not stop:
        stop = (
            f"Só {len(chosen)} ativos aptos (o mínimo é {params.k_min})."
            if len(chosen) < params.k_min
            else f"Todos os {len(chosen)} ativos possíveis entraram: cada um ainda melhorava a "
            "utilidade."
        )
    skipped += [SkippedAsset(r.ticker, "Ficou fora. " + stop) for r in remaining]
    return ClassConstruction(
        arca_class=matrix.arca_class,
        as_of=matrix.as_of,
        k=len(chosen),
        stop_reason=stop,
        confidence=round(sum(weights[r.ticker] * r.confidence for r in chosen), 4),
        selected=[
            SelectedAsset(
                ticker=r.ticker,
                sector=sectors[r.ticker],
                group=groups[r.ticker],
                weight=round(weights[r.ticker], 6),
                score=r.score,
                expected=r.expected,
                confidence=r.confidence,
                reason=reasons.get(r.ticker, ""),
            )
            for r in chosen
        ],
        skipped=skipped,
        curve=curve,
        notes=notes,
    )


def pulled_targets(
    construction: ClassConstruction,
    current: Mapping[str, float],
    weights: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Final targets: the construction (or `weights`, the optimizer's) pulled toward the current
    weights by the confidence (decision 10.6); an asset held but not selected keeps only the
    current share left."""
    held = sum(v for v in current.values() if v > 0)
    now = {t: v / held for t, v in current.items() if v > 0} if held > 0 else {}
    c = construction.confidence if now else 1.0
    new = dict(weights) if weights else {s.ticker: s.weight for s in construction.selected}
    tickers = set(new) | set(now)
    targets = {t: c * new.get(t, 0.0) + (1.0 - c) * now.get(t, 0.0) for t in tickers}
    total = sum(targets.values()) or 1.0
    return {t: round(w / total, 6) for t, w in targets.items() if w > 0}
