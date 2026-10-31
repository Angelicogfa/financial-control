"""Walk-forward backtest of the recommendation and the scoreboard of its runs (Phase 45.6).

Backtest (the Ações class, where the point-in-time panel exists). Every quarter of the past, with
only what was known that month:

- the universe is the panel's companies with at least 12 months of prices and no judicial
  recovery or debt restructuring announced in the previous two years (the gates that can be
  rebuilt for the past; liquidity uses today's universe, a survivorship caveat);
- the lenses are the panel's signals of that month (quality, valuation, improvement, momentum,
  income, risk), combined with the AHP weights of the class's objective. The manual Cerrado and
  the projection stay out (decision 10.3: the answers and the price forecast have no past), so
  their weights are spread over the other lenses;
- the weights come from the same construction (sector rule, dynamic K, caps), on the 40 best
  scores and the returns up to that month;
- the portfolio is held for three months and its monthly return over the class is compared
  with equal weights over every eligible asset ("pesos iguais", the reference the past allows:
  the Cerrado rule needs answers that were never dated).

The verdict uses the Lab's Bayesian gate on the paired monthly differences: the hierarchy beats
equal weights out of sample when P(difference > 0) is at least 90% over at least five years.
"It does not improve" is a valid result.

Scoreboard (the runs from now on): for each stored run, the chosen weights are measured 1, 3, 6
and 12 months later against equal weights over the eligible assets of that run and against an
approximation of the current rule (the registered assets weighted by their Cerrado score).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from typing import Any

import numpy as np

from domain.recommendation.combination import combine_class
from domain.recommendation.construction import build_class
from domain.recommendation.gates import PASS, AssetGates, GateResult
from domain.recommendation.keys import CERRADO, PROJECTION
from domain.recommendation.lenses import LENS_SIGNALS, AssetLenses, LensScore
from domain.recommendation.params import ConstructionParams
from domain.simulation.bayes import credible_interval
from domain.simulation.validation import bayesian_gate

Month = tuple[int, int]

HOLD_MONTHS = 3
TOP_CANDIDATES = 40
MIN_COMPANIES = 20
MIN_HISTORY_MONTHS = 12
RESTRUCTURING_MONTHS = 24
MIN_YEARS = 5
MIN_PROBABILITY = 0.9
SCOREBOARD_HORIZONS = (1, 3, 6, 12)
LEFT_OUT = (CERRADO, PROJECTION)


def add_months(month: Month, n: int) -> Month:
    index = month[0] * 12 + (month[1] - 1) + n
    return (index // 12, index % 12 + 1)


def _months_between(a: Month, b: Month) -> int:
    return (b[0] - a[0]) * 12 + (b[1] - a[1])


def backtest_weights(weights: Mapping[str, float]) -> dict[str, float]:
    """The AHP weights without the lenses that have no past, rescaled to 1."""
    kept = {lens: w for lens, w in weights.items() if lens not in LEFT_OUT}
    total = sum(kept.values()) or 1.0
    return {lens: w / total for lens, w in kept.items()}


@dataclass(frozen=True)
class YearLine:
    year: int
    months: int
    strategy: float  # compounded return over the class in the year
    equal: float


@dataclass(frozen=True)
class Backtest:
    as_of: date
    status: str  # OK or INSUFFICIENT
    passed: bool
    reason: str
    first_month: str | None = None
    last_month: str | None = None
    months: int = 0
    rebalances: int = 0
    average_k: float = 0.0
    strategy_annual: float = 0.0  # mean monthly return over the class x 12
    equal_annual: float = 0.0
    difference_annual: float = 0.0
    hit_rate: float = 0.0  # share of months the hierarchy beat equal weights
    probability: float = 0.5  # P(mean difference > 0), Bayesian bootstrap
    years: list[YearLine] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["as_of"] = self.as_of.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Backtest:
        payload = dict(data)
        payload["as_of"] = date.fromisoformat(payload["as_of"])
        payload["years"] = [YearLine(**y) for y in payload.get("years", [])]
        return cls(**payload)


def _lenses(ticker: str, month: Month, signals: Mapping[str, float], sector: str) -> AssetLenses:
    scores = []
    for lens, signal in LENS_SIGNALS.items():
        z = signals.get(signal)
        if z is None:
            scores.append(LensScore(lens, None, None, 0.0, ""))
        else:
            clipped = max(min(z, 3.0), -3.0)
            scores.append(LensScore(lens, clipped, (clipped + 3.0) / 6.0, 1.0, ""))
    as_of = date(month[0], month[1], 1)
    return AssetLenses(ticker, as_of, "CATALOG", "ACOES", sector, scores)


def _eligible(
    tickers: Sequence[str],
    month: Month,
    first_month: Mapping[str, Month],
    restructuring: Mapping[str, Sequence[Month]],
) -> list[str]:
    out = []
    for t in tickers:
        first = first_month.get(t)
        if first is None or _months_between(first, month) < MIN_HISTORY_MONTHS:
            continue
        if any(
            0 <= _months_between(m, month) < RESTRUCTURING_MONTHS for m in restructuring.get(t, ())
        ):
            continue
        out.append(t)
    return out


def run_backtest(
    *,
    as_of: date,
    panel: Mapping[Month, Mapping[str, Mapping[str, float]]],
    alphas: Mapping[str, Mapping[Month, float]],
    returns: Mapping[str, Mapping[Month, float]],
    sectors: Mapping[str, str],
    first_month: Mapping[str, Month],
    restructuring: Mapping[str, Sequence[Month]],
    weights: Mapping[str, float],
    params: ConstructionParams,
    scale_annual: float,
    seed: int = 7,
) -> Backtest:
    """Quarterly rebalanced walk-forward of the hierarchy against equal weights."""
    used = backtest_weights(weights)
    months = sorted(m for m, rows in panel.items() if len(rows) >= MIN_COMPANIES)
    strategy: list[float] = []
    equal: list[float] = []
    stamps: list[Month] = []
    ks: list[int] = []
    rebalance = 0
    i = 0
    while i < len(months):
        month = months[i]
        tickers = _eligible(sorted(panel[month]), month, first_month, restructuring)
        if len(tickers) < MIN_COMPANIES:
            i += 1
            continue
        items = [_lenses(t, month, panel[month][t], sectors.get(t, "")) for t in tickers]
        gates = {t: AssetGates(t, [GateResult("HISTORY", PASS, "")]) for t in tickers}
        matrix = combine_class(
            arca_class="ACOES",
            objective="BACKTEST",
            as_of=date(month[0], month[1], 1),
            weights=used,
            consistency_ratio=0.0,
            scale_annual=scale_annual,
            items=items,
            gates=gates,
        )
        top = replace(matrix, rows=matrix.rows[:TOP_CANDIDATES])
        known = {t: {m: r for m, r in returns.get(t, {}).items() if m <= month} for t in tickers}
        built = build_class(top, known, params)
        target = {s.ticker: s.weight for s in built.selected}
        if not target:
            i += 1
            continue
        rebalance += 1
        ks.append(built.k)
        for h in range(1, HOLD_MONTHS + 1):
            nxt = add_months(month, h)
            held = {t: w for t, w in target.items() if nxt in alphas.get(t, {})}
            universe = [alphas[t][nxt] for t in tickers if nxt in alphas.get(t, {})]
            if not held or not universe:
                continue
            total = sum(held.values())
            strategy.append(sum(w / total * alphas[t][nxt] for t, w in held.items()))
            equal.append(float(np.mean(universe)))
            stamps.append(nxt)
        # Hold for the quarter: the next rebalance is three months later.
        target_month = add_months(month, HOLD_MONTHS)
        while i < len(months) and months[i] < target_month:
            i += 1
    notes = [
        "Ficam de fora o Cerrado manual (sem respostas datadas) e a projeção (a previsão de "
        "preço só existe de 2026 em diante); seus pesos foram repartidos entre as outras lentes.",
        "A liquidez usa o universo de hoje: empresas que deixaram de ser negociadas não entram "
        "(viés de sobrevivência).",
        "Sem custos de negociação: as duas carteiras são refeitas a cada trimestre.",
    ]
    if len(strategy) < 2:
        return Backtest(
            as_of,
            "INSUFFICIENT",
            False,
            "Histórico insuficiente para testar a hierarquia no passado: faltam meses com ao "
            f"menos {MIN_COMPANIES} empresas no painel de sinais.",
            weights=used,
            notes=notes,
        )
    s, e = np.array(strategy), np.array(equal)
    gate = bayesian_gate(s, e, seed=seed)
    years_tested = len(strategy) / 12.0
    passed = gate.probability >= MIN_PROBABILITY and years_tested >= MIN_YEARS
    diff_annual = float((s - e).mean() * 12.0)
    if years_tested < MIN_YEARS:
        reason = (
            f"Só {years_tested:.1f} anos testados; são precisos {MIN_YEARS} para um veredito."
        ).replace(".", ",", 1)
    elif passed:
        reason = (
            f"A hierarquia superou os pesos iguais em {diff_annual:+.1%} ao ano, com "
            f"{gate.probability:.0%} de confiança, em {years_tested:.0f} anos fora da amostra."
        )
    else:
        reason = (
            f"A hierarquia não superou os pesos iguais com confiança: diferença de "
            f"{diff_annual:+.1%} ao ano e {gate.probability:.0%} de chance de ser positiva "
            f"(são precisos {MIN_PROBABILITY:.0%})."
        )
    by_year: dict[int, list[tuple[float, float]]] = {}
    for stamp, a, b in zip(stamps, strategy, equal, strict=True):
        by_year.setdefault(stamp[0], []).append((a, b))
    years = [
        YearLine(
            year=y,
            months=len(pairs),
            strategy=round(float(np.prod([1 + a for a, _ in pairs]) - 1), 6),
            equal=round(float(np.prod([1 + b for _, b in pairs]) - 1), 6),
        )
        for y, pairs in sorted(by_year.items())
    ]
    return Backtest(
        as_of=as_of,
        status="OK",
        passed=passed,
        reason=reason,
        first_month=f"{stamps[0][0]}-{stamps[0][1]:02d}",
        last_month=f"{stamps[-1][0]}-{stamps[-1][1]:02d}",
        months=len(strategy),
        rebalances=rebalance,
        average_k=round(float(np.mean(ks)), 2) if ks else 0.0,
        strategy_annual=round(float(s.mean() * 12.0), 6),
        equal_annual=round(float(e.mean() * 12.0), 6),
        difference_annual=round(diff_annual, 6),
        hit_rate=round(float((s > e).mean()), 4),
        probability=gate.probability,
        years=years,
        weights={k: round(v, 6) for k, v in used.items()},
        notes=notes,
    )


# --- scoreboard --------------------------------------------------------------------------------


@dataclass(frozen=True)
class RunPortfolios:
    """What one stored run would have held, and its references."""

    as_of: date
    recommended: dict[str, float]  # ticker -> weight
    eligible: list[str]  # equal weights over these
    cerrado: dict[str, float]  # registered assets by their Cerrado score (approximation)


@dataclass(frozen=True)
class ScoreLine:
    horizon: int  # months after the run
    runs: int
    vs_equal: float  # mean return difference over the horizon
    beat_equal: float  # share of runs ahead
    beat_equal_low: float
    beat_equal_high: float
    vs_cerrado: float | None = None
    beat_cerrado: float | None = None
    cerrado_runs: int = 0


def _forward(
    weights: Mapping[str, float],
    returns: Mapping[str, Mapping[Month, float]],
    start: Month,
    horizon: int,
) -> float | None:
    """Compounded return of fixed weights over the `horizon` months after `start`."""
    growth = 1.0
    for h in range(1, horizon + 1):
        m = add_months(start, h)
        held = {t: w for t, w in weights.items() if m in returns.get(t, {})}
        total = sum(held.values())
        if total <= 0:
            return None
        growth *= 1.0 + sum(w / total * returns[t][m] for t, w in held.items())
    return growth - 1.0


def scoreboard(
    runs: Sequence[RunPortfolios],
    returns: Mapping[str, Mapping[Month, float]],
    last_month: Month,
) -> list[ScoreLine]:
    """How the past runs did 1, 3, 6 and 12 months later."""
    out = []
    for horizon in SCOREBOARD_HORIZONS:
        diffs, wins, c_diffs, c_wins = [], 0, [], 0
        for run in runs:
            start = (run.as_of.year, run.as_of.month)
            if _months_between(start, last_month) < horizon or not run.recommended:
                continue
            mine = _forward(run.recommended, returns, start, horizon)
            base = _forward(dict.fromkeys(run.eligible, 1.0), returns, start, horizon)
            if mine is None or base is None:
                continue
            diffs.append(mine - base)
            wins += mine > base
            if run.cerrado:
                rule = _forward(run.cerrado, returns, start, horizon)
                if rule is not None:
                    c_diffs.append(mine - rule)
                    c_wins += mine > rule
        if not diffs:
            continue
        low, high = credible_interval(wins, len(diffs))
        out.append(
            ScoreLine(
                horizon=horizon,
                runs=len(diffs),
                vs_equal=round(float(np.mean(diffs)), 6),
                beat_equal=round(wins / len(diffs), 4),
                beat_equal_low=round(low, 4),
                beat_equal_high=round(high, 4),
                vs_cerrado=round(float(np.mean(c_diffs)), 6) if c_diffs else None,
                beat_cerrado=round(c_wins / len(c_diffs), 4) if c_diffs else None,
                cerrado_runs=len(c_diffs),
            )
        )
    return out
