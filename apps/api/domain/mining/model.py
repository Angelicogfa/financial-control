"""Weights, gates, overfitting and costs of the Garimpo (Phase 43.3).

Weights: every month, the return over the class in the next 12 months is regressed on the four
signals across the companies (missing signals count as 0, the sector average); the monthly
coefficients are averaged (Fama-MacBeth), their error widened for the overlap of the 12-month
windows, and each is shrunk by a sceptical prior N(0, 0.2% a month). A signal whose sign is not
clear (< 90%) gets weight 0.

Out of sample, by rolling origin: each December the weights are estimated with the windows that
had closed, and every month of the next year the 10 best scores are the findings. Their return
over the class in the following 12 months is compared with the average of the whole universe
(what a random pick of the same universe gets) and charged a trading cost.

Overfitting: the same backtest runs for every subset of signals and 5, 10 or 20 findings, and
the months are split in halves every way (CSCV, as in the Lab). Two numbers come out: the PBO,
the chance that the variant that looks best in one half is below the median in the other, and
the chance that it loses to the universe in the other half. Many variants share the same good
signal and do about as well, so the best one landing near the median (PBO near 50%) is
indifference, not overfitting; what the gate asks is that the chosen variant rarely loses.

Gate: the mining shows findings only if, out of sample and after costs, the findings beat the
universe with at least 90% probability, the chosen variant loses to the universe in at most a
quarter of the CSCV splits, and there are at least five years to judge.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import numpy as np

from domain.forecast.valuation_model import (
    FORWARD_MONTHS,
    MIN_COMPANIES,
    PRIOR_SD,
    Month,
    add_months,
    fama_macbeth,
    posterior,
)
from domain.mining.signals import SIGNALS
from domain.simulation.validation import pbo_cscv

MIN_SIGN_PROBABILITY = 0.9
MIN_ORIGINS = 5
MAX_LOSS_PROBABILITY = 0.25
MIN_EXCESS_PROBABILITY = 0.9
COST_ANNUAL = 0.006  # round trip of a yearly turnover, with spread and impact on liquid stocks
FINDINGS = 10  # decision 43.0-2
VARIANT_SIZES = (5, 10, 20)

Signals = Mapping[str, Mapping[Month, Mapping[str, float]]]
Forward = Mapping[str, Mapping[Month, float]]


def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass(frozen=True)
class SignalWeight:
    signal: str
    estimate: float  # posterior mean, monthly return over the class per unit of z
    sd: float
    sign_probability: float
    weight: float  # 0 when the sign is not clear
    months: int


CoefficientTable = dict[Month, dict[str, float]]


def coefficient_table(
    signals: Signals, forward: Forward, months: Sequence[Month], names: Sequence[str]
) -> CoefficientTable:
    """One cross-sectional regression a month: next-12-month return on the signals.

    Computed once per set of signals; every origin of the backtest reads the months it may use.
    """
    out: CoefficientTable = {}
    k = len(names)
    for month in months:
        rows, ys = [], []
        for t, by_month in signals.items():
            values = by_month.get(month)
            y = forward.get(t, {}).get(month)
            if values is None or y is None:
                continue
            rows.append([values.get(n, 0.0) for n in names])
            ys.append(y)
        if len(ys) < max(MIN_COMPANIES, k + 3):
            continue
        x = np.column_stack([np.ones(len(ys)), np.array(rows)])
        coef, *_ = np.linalg.lstsq(x, np.array(ys), rcond=None)
        out[month] = {n: float(coef[i + 1]) for i, n in enumerate(names)}
    return out


def weights_from(
    table: CoefficientTable, months: Sequence[Month], names: Sequence[str]
) -> dict[str, SignalWeight]:
    """Fama-MacBeth means of the months given, shrunk by the prior; unclear signs get 0."""
    rows = [table[m] for m in months if m in table]
    weights: dict[str, SignalWeight] = {}
    for name in names:
        slope = fama_macbeth([r[name] for r in rows])
        if slope is None:
            weights[name] = SignalWeight(name, 0.0, PRIOR_SD, 0.5, 0.0, 0)
            continue
        mean, sd = posterior(slope, 0.0, PRIOR_SD)
        sign = _phi(abs(mean) / sd)
        weights[name] = SignalWeight(
            name,
            mean,
            sd,
            round(sign, 4),
            mean if sign >= MIN_SIGN_PROBABILITY else 0.0,
            slope.months,
        )
    return weights


def estimate_weights(
    signals: Signals, forward: Forward, months: Sequence[Month], names: Sequence[str] = SIGNALS
) -> dict[str, SignalWeight]:
    return weights_from(coefficient_table(signals, forward, months, names), months, names)


def score(values: Mapping[str, float], weights: Mapping[str, float]) -> float:
    return float(sum(w * values.get(name, 0.0) for name, w in weights.items()))


def ranking(
    signals: Signals, month: Month, weights: Mapping[str, float]
) -> list[tuple[str, float]]:
    """Companies with signals that month, best score first."""
    rows = [
        (t, score(by_month[month], weights)) for t, by_month in signals.items() if month in by_month
    ]
    return sorted(rows, key=lambda r: -r[1])


def _variant_returns(
    signals: Signals,
    forward: Forward,
    months: Sequence[Month],
    names: Sequence[str],
    size: int,
    table: CoefficientTable | None = None,
) -> dict[Month, float]:
    """Monthly return over the universe of the `size` best, out of sample, after costs."""
    table = table if table is not None else coefficient_table(signals, forward, months, names)
    out: dict[Month, float] = {}
    years = sorted({m[0] for m in months})
    for year in years:
        origin = (year, 12)
        train = [m for m in months if add_months(m, FORWARD_MONTHS) <= origin]
        test = [m for m in months if origin < m <= add_months(origin, 12)]
        if len(train) < 24 or not test:
            continue
        found = weights_from(table, train, names)
        weights = {n: w.weight for n, w in found.items()}
        if not any(weights.values()):
            weights = {n: w.estimate for n, w in found.items()}  # still rank, gate decides later
        for month in test:
            ranked = [
                (t, s) for t, s in ranking(signals, month, weights) if month in forward.get(t, {})
            ]
            if len(ranked) < max(MIN_COMPANIES, size * 2):
                continue
            universe = float(np.mean([forward[t][month] for t, _ in ranked]))
            picked = float(np.mean([forward[t][month] for t, _ in ranked[:size]]))
            out[month] = picked - universe - COST_ANNUAL / 12.0
    return out


@dataclass(frozen=True)
class MiningModel:
    as_of: date
    weights: dict[str, float]  # used to rank (0 for a signal whose sign is not clear)
    signals: list[SignalWeight] = field(default_factory=list)
    oos_months: int = 0
    oos_excess_annual: float = 0.0  # findings over the universe, after costs
    oos_probability: float = 0.5  # P(excess > 0)
    oos_hit_rate: float = 0.0  # share of months the findings beat the universe
    pbo: float | None = None
    loss_probability: float | None = None  # CSCV: the in-sample best loses out of sample
    variants: int = 0
    cost_annual: float = COST_ANNUAL
    passed: bool = False
    reason: str = ""
    record: list[dict[str, Any]] = field(default_factory=list)  # 43.5, see findings.record

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["as_of"] = self.as_of.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MiningModel:
        payload = dict(data)
        payload["as_of"] = date.fromisoformat(payload["as_of"])
        payload["signals"] = [SignalWeight(**s) for s in payload.get("signals", [])]
        return cls(**payload)


def estimate_mining_model(signals: Signals, forward: Forward, *, as_of: date) -> MiningModel:
    months = sorted({m for by_month in signals.values() for m in by_month})
    closed = [m for m in months if any(m in forward.get(t, {}) for t in signals)]
    full = coefficient_table(signals, forward, closed, SIGNALS)
    found = weights_from(full, closed, SIGNALS)
    weights = {n: w.weight for n, w in found.items()}
    base: dict[str, Any] = {"as_of": as_of, "weights": weights, "signals": list(found.values())}

    main = _variant_returns(signals, forward, closed, SIGNALS, FINDINGS, full)
    origins = len({m[0] for m in main})
    if not main:
        return MiningModel(
            **base, reason="Ainda não há anos fora da amostra para julgar os achados."
        )
    series = np.array([main[m] for m in sorted(main)])
    effective = max(len(series) / FORWARD_MONTHS, 1.0)
    sd = float(np.std(series, ddof=1)) if len(series) > 1 else 0.0
    mean = float(series.mean())
    probability = _phi(mean / (sd / math.sqrt(effective))) if sd > 0 else (1.0 if mean > 0 else 0.0)
    hit = float((series > 0).mean())

    variants = [
        (subset, size)
        for r in range(1, len(SIGNALS) + 1)
        for subset in itertools.combinations(SIGNALS, r)
        for size in VARIANT_SIZES
    ]
    tables = {subset: coefficient_table(signals, forward, closed, subset) for subset, _ in variants}
    columns = [
        _variant_returns(signals, forward, closed, subset, size, tables[subset])
        for subset, size in variants
    ]
    # A variant that never had enough companies (20 findings in a small universe) sits out.
    columns = [c for c in columns if c]
    common = sorted(set.intersection(*(set(c) for c in columns))) if columns else []
    pbo = loss = None
    if len(columns) >= 2 and len(common) >= 8:
        matrix = np.array([[c[m] for c in columns] for m in common])
        overfit = pbo_cscv(matrix)
        pbo, loss = overfit.pbo, overfit.loss_probability

    stats = {
        "oos_months": len(series),
        "oos_excess_annual": round((1.0 + mean) ** 12 - 1.0, 6),
        "oos_probability": round(probability, 4),
        "oos_hit_rate": round(hit, 4),
        "pbo": pbo,
        "loss_probability": loss,
        "variants": len(variants),
    }
    excess = stats["oos_excess_annual"]
    if origins < MIN_ORIGINS:
        passed, reason = False, f"Só {origins} anos fora da amostra; são precisos {MIN_ORIGINS}."
    elif probability < MIN_EXCESS_PROBABILITY:
        passed, reason = (
            False,
            f"Fora da amostra, os achados renderam {excess:+.1%} ao ano sobre o "
            f"universo depois dos custos, com {probability:.0%} de confiança: não basta para "
            "mostrar achados.",
        )
    elif loss is None:
        passed, reason = False, "Meses insuficientes para medir o risco de sobreajuste."
    elif loss > MAX_LOSS_PROBABILITY:
        passed, reason = (
            False,
            f"A melhor variante no passado perdeu do universo em {loss:.0%} das metades de "
            "teste: os achados poderiam ser sorte.",
        )
    else:
        passed, reason = (
            True,
            f"Fora da amostra, os achados renderam {excess:+.1%} ao ano sobre o "
            f"universo depois dos custos ({probability:.0%} de confiança; a melhor variante "
            f"perdeu do universo em {loss:.0%} das metades de teste).",
        )
    return MiningModel(**base, **stats, passed=passed, reason=reason)
