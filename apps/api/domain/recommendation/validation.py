"""Lens weights validated by the data (Phase 45.7, design N5 form 2).

The declared weights (classic AHP, 45.3) are the prior; the data may move them only through an
out-of-sample gate:

1. What the data say: for the six lenses with a past (quality, valuation, improvement, momentum,
   income, risk), the monthly cross-sectional regression of the next 12 months' return over the
   class on the lenses' z, averaged by Fama-MacBeth and shrunk by a sceptical prior (the
   Garimpo's estimation, 43.3). A lens whose sign is not clear (under 90%), or that hurts, gets
   weight 0 from the data.
2. The candidate, sceptical: half the declared weights, half the data's, over those six lenses;
   the Cerrado and the projection keep their declared weight (they have no past to test).
3. The gate, by yearly rolling origin: each December the data weights are estimated with the
   windows that had closed, and every month of the next year the 10 best scores are compared
   with the universe, with the candidate and with the declared weights, on the next month's
   return over the class (one month ahead, so the months do not overlap). The candidate replaces
   the declared weights when it beats them with at least 90% probability (the Lab's Bayesian gate)
   over at least five years. "The data did not justify changing your weights" is a valid result.

The validated weights apply to the Ações class (the only one with the point-in-time panel) and
only under the GROWTH or MIXED objectives: the test measures total return, which would override
a DIVIDENDS choice.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import numpy as np

from domain.forecast.valuation_model import FORWARD_MONTHS, Month, add_months
from domain.mining.model import MIN_SIGN_PROBABILITY, coefficient_table, ranking, weights_from
from domain.recommendation.keys import DIVIDENDS
from domain.recommendation.lenses import LENS_SIGNALS
from domain.simulation.validation import bayesian_gate

LENS_WEIGHTS = "LENS_WEIGHTS"  # the stored model (forecast_models)
TOP = 10
MIN_ORIGINS = 5
MIN_PROBABILITY = 0.9
MIN_UNIVERSE = 20
DATA_SHARE = 0.5  # how far the candidate moves from the declared weights toward the data's


@dataclass(frozen=True)
class LensWeightLine:
    lens: str
    declared: float
    estimate_annual_per_z: float  # what the data say: extra return a year per unit of z
    sign_probability: float
    data: float  # the data's weight (0 when the sign is not clear or it hurts)
    candidate: float
    used: float


@dataclass(frozen=True)
class LensWeights:
    as_of: date
    objective: str
    passed: bool
    reason: str
    origins: int = 0
    oos_months: int = 0
    improvement_annual: float = 0.0  # candidate's top 10 over the declared's, a year
    probability: float = 0.5
    lines: list[LensWeightLine] = field(default_factory=list)
    used: dict[str, float] = field(default_factory=dict)  # every lens, summing to 1

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["as_of"] = self.as_of.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LensWeights:
        payload = dict(data)
        payload["as_of"] = date.fromisoformat(payload["as_of"])
        payload["lines"] = [LensWeightLine(**line) for line in payload.get("lines", [])]
        return cls(**payload)


Panel = Mapping[str, Mapping[Month, Mapping[str, float]]]  # ticker -> month -> signal -> z


def _data_weights(estimates: Mapping[str, Any], share: float) -> dict[str, float]:
    """Positive, clear slopes as weights over the six lenses, summing to `share`."""
    raw = {}
    for lens, signal in LENS_SIGNALS.items():
        found = estimates[signal]
        raw[lens] = found.estimate if found.sign_probability >= MIN_SIGN_PROBABILITY else 0.0
        raw[lens] = max(raw[lens], 0.0)
    total = sum(raw.values())
    return {lens: share * v / total for lens, v in raw.items()} if total > 0 else {}


def candidate_weights(
    declared: Mapping[str, float], estimates: Mapping[str, Any]
) -> tuple[dict[str, float], dict[str, float]]:
    """(data weights, candidate weights) for every lens; empty data when the data say nothing."""
    share = sum(declared.get(lens, 0.0) for lens in LENS_SIGNALS)
    data = _data_weights(estimates, share)
    if not data:
        return {}, dict(declared)
    candidate = dict(declared)
    for lens in LENS_SIGNALS:
        candidate[lens] = (1 - DATA_SHARE) * declared.get(lens, 0.0) + DATA_SHARE * data[lens]
    return data, candidate


def _signal_weights(weights: Mapping[str, float]) -> dict[str, float]:
    """Lens weights as weights on the panel's signals (the score of the ranking)."""
    return {signal: weights.get(lens, 0.0) for lens, signal in LENS_SIGNALS.items()}


def _top_over_universe(
    panel: Panel,
    alphas: Mapping[str, Mapping[Month, float]],
    month: Month,
    weights: Mapping[str, float],
) -> float | None:
    nxt = add_months(month, 1)
    ranked = [
        (t, s)
        for t, s in ranking(panel, month, _signal_weights(weights))
        if nxt in alphas.get(t, {})
    ]
    if len(ranked) < max(MIN_UNIVERSE, TOP * 2):
        return None
    universe = float(np.mean([alphas[t][nxt] for t, _ in ranked]))
    return float(np.mean([alphas[t][nxt] for t, _ in ranked[:TOP]])) - universe


def validate_lens_weights(
    *,
    as_of: date,
    objective: str,
    declared: Mapping[str, float],
    panel: Panel,
    alphas: Mapping[str, Mapping[Month, float]],
    forward: Mapping[str, Mapping[Month, float]],
    seed: int = 11,
) -> LensWeights:
    """The data's view of the lens weights and whether it passes the out-of-sample gate."""
    names = list(LENS_SIGNALS.values())
    months = sorted({m for by_month in panel.values() for m in by_month})
    table = coefficient_table(panel, forward, months, names)
    full = weights_from(table, months, names)
    data, candidate = candidate_weights(declared, full)

    cand_series: list[float] = []
    decl_series: list[float] = []
    origins = 0
    for year in sorted({m[0] for m in months}):
        origin = (year, 12)
        train = [m for m in months if add_months(m, FORWARD_MONTHS) <= origin]
        test = [m for m in months if origin < m <= add_months(origin, 12)]
        if len(train) < 24 or not test:
            continue
        _d, past_candidate = candidate_weights(declared, weights_from(table, train, names))
        used_year = False
        for month in test:
            a = _top_over_universe(panel, alphas, month, past_candidate)
            b = _top_over_universe(panel, alphas, month, declared)
            if a is None or b is None:
                continue
            cand_series.append(a)
            decl_series.append(b)
            used_year = True
        origins += used_year

    lines = [
        LensWeightLine(
            lens=lens,
            declared=round(declared.get(lens, 0.0), 6),
            estimate_annual_per_z=round(full[signal].estimate * 12.0, 6),
            sign_probability=full[signal].sign_probability,
            data=round(data.get(lens, 0.0), 6),
            candidate=round(candidate.get(lens, 0.0), 6),
            used=0.0,
        )
        for lens, signal in LENS_SIGNALS.items()
    ]

    def result(passed: bool, reason: str, **extra: Any) -> LensWeights:
        used = dict(candidate if passed else declared)
        return LensWeights(
            as_of=as_of,
            objective=objective,
            passed=passed,
            reason=reason,
            lines=[
                LensWeightLine(**{**asdict(line), "used": round(used.get(line.lens, 0.0), 6)})
                for line in lines
            ],
            used={k: round(v, 6) for k, v in used.items()},
            **extra,
        )

    if objective == DIVIDENDS:
        return result(
            False,
            "O objetivo da classe é Dividendos: o teste mede retorno total e não muda essa "
            "escolha.",
        )
    if not data:
        return result(
            False, "Os dados não mostram um efeito claro de nenhuma lente: ficam os seus pesos."
        )
    if len(cand_series) < 2:
        return result(False, "Histórico insuficiente para testar os pesos fora da amostra.")
    gate = bayesian_gate(np.array(cand_series), np.array(decl_series), seed=seed)
    improvement = float((np.array(cand_series) - np.array(decl_series)).mean() * 12.0)
    extra = {
        "origins": origins,
        "oos_months": len(cand_series),
        "improvement_annual": round(improvement, 6),
        "probability": gate.probability,
    }
    if origins < MIN_ORIGINS:
        return result(
            False, f"Só {origins} anos fora da amostra; são precisos {MIN_ORIGINS}.", **extra
        )
    if gate.probability < MIN_PROBABILITY:
        return result(
            False,
            f"Os dados não justificaram mudar os seus pesos: os pesos ajustados renderam "
            f"{improvement:+.1%} ao ano a mais nas 10 melhores notas, com {gate.probability:.0%} "
            f"de confiança (são precisos {MIN_PROBABILITY:.0%}).",
            **extra,
        )
    return result(
        True,
        f"Os pesos ajustados pelos dados renderam {improvement:+.1%} ao ano a mais nas 10 "
        f"melhores notas, com {gate.probability:.0%} de confiança em {origins} anos fora da "
        "amostra: passam a ser usados na classe Ações.",
        **extra,
    )
