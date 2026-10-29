"""The laboratory: score every regime and risk model out of sample and apply the gates.

Target: the monthly return in excess of the CDI of the model portfolio (the policy targets),
the same series the calibration (33.6) uses. Each model's gain is its one-step-ahead log
score minus the reference's, month by month, from walk-forward forecasts (labels of one
month: nothing to purge). Gates of design 7.2, all required:
1. P(mean gain > 0) of at least 95% by the Bayesian bootstrap (6.5);
2. a significant deflated Sharpe of the gain series, with every laboratory trial counted;
3. CSCV across the models on the gain series: the model chosen in sample must lose to the
   reference out of sample in less than 20% of the splits. The classic PBO is reported too,
   but not gated: when several models are alike and all beat the reference, picking the
   best of them adds nothing and PBO stays near 50% although every one of them is useful;
4. stability: gate 1 still passes with the first forecast moved 12 months earlier and later.
No model feeds layer B unless it passes all; "no model passed" is a valid result.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from domain.shared.enums import ArcaClass
from domain.simulation.engine import SimulationTimeout
from domain.simulation.ml.models import MODELS, fit_hmm, forecast_logscores, hmm_filter
from domain.simulation.scenarios import CLASS_ORDER, ClassSample, InsufficientHistory
from domain.simulation.validation import bayesian_gate, deflated_sharpe, pbo_cscv, sharpe

MIN_TRAIN_MONTHS = 60
STABILITY_SHIFT = 12
PBO_LIMIT = 0.20


@dataclass(frozen=True)
class ModelVerdict:
    key: str
    label: str
    family: str
    months: int
    mean_gain: float  # nats a month over the reference
    gate_probability: float
    deflated_probability: float
    stable: bool
    passed: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RegimePoint:
    month: date
    stress_probability: float  # P(worst regime | history up to the month), 2-state HMM


@dataclass(frozen=True)
class LabResult:
    months: int
    first_forecast: date
    last_forecast: date
    trials: int  # this run plus every earlier laboratory run
    pbo: float | None
    loss_probability: float | None
    models: list[ModelVerdict]
    approved: list[str]
    regime: list[RegimePoint]
    regime_means: list[float]
    verdict: str
    warnings: list[str]


def portfolio_series(sample: ClassSample, targets: Mapping[ArcaClass, float]) -> np.ndarray:
    weights = np.array([targets.get(c, 0.0) for c in CLASS_ORDER])
    weights = weights / weights.sum()
    return sample.excess @ weights


def run_lab(
    sample: ClassSample,
    targets: Mapping[ArcaClass, float],
    *,
    prior_trials: int,
    seed: int,
    min_train: int = MIN_TRAIN_MONTHS,
    deadline: Callable[[], bool] | None = None,
) -> LabResult:
    y = portfolio_series(sample, targets)
    needed = min_train + STABILITY_SHIFT + 24
    if y.size < needed:
        raise InsufficientHistory(
            f"O laboratório precisa de {needed} meses de histórico comum; há {y.size}."
        )
    start = min_train
    reference = forecast_logscores(y, None, start=start - STABILITY_SHIFT)
    gains: dict[str, np.ndarray] = {}
    shifted: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for spec in MODELS:
        if deadline is not None and deadline():
            raise SimulationTimeout(f"laboratory stopped at {spec.key}")
        scores = forecast_logscores(y, spec, start=start - STABILITY_SHIFT)
        diff = scores - reference  # from start - 12
        gains[spec.key] = diff[STABILITY_SHIFT:]  # the main window starts at `start`
        shifted[spec.key] = (diff, diff[2 * STABILITY_SHIFT :])

    trials = prior_trials + len(MODELS)
    matrix = np.column_stack([gains[s.key] for s in MODELS])
    cscv = pbo_cscv(matrix) if matrix.shape[0] >= 4 else None
    pbo = cscv.pbo if cscv else None
    loss = cscv.loss_probability if cscv else None
    all_sharpes = [sharpe(gains[s.key]) for s in MODELS]

    verdicts: list[ModelVerdict] = []
    for j, spec in enumerate(MODELS):
        g = gains[spec.key]
        gate = bayesian_gate(g, np.zeros_like(g), seed=seed + j)
        dsr = deflated_sharpe(g, all_sharpes, n_trials=trials)
        earlier, later = shifted[spec.key]
        stable = all(
            bayesian_gate(s, np.zeros_like(s), seed=seed + 100 + j).passed for s in (earlier, later)
        )
        reasons = []
        if not gate.passed:
            reasons.append(
                f"chance de superar a referência de {gate.probability:.0%} (precisa de 95%)"
            )
        if not dsr.significant:
            reasons.append(f"Sharpe deflacionado de {dsr.probability:.0%} com {trials} tentativas")
        if loss is not None and loss >= PBO_LIMIT:
            reasons.append(
                f"o modelo escolhido perde para a referência fora da amostra em {loss:.0%} das "
                "divisões (precisa ficar abaixo de 20%)"
            )
        if not stable:
            reasons.append("o resultado muda com a data de corte deslocada 12 meses")
        verdicts.append(
            ModelVerdict(
                key=spec.key,
                label=spec.label,
                family=spec.family,
                months=int(g.size),
                mean_gain=round(float(g.mean()), 5),
                gate_probability=gate.probability,
                deflated_probability=dsr.probability,
                stable=stable,
                passed=not reasons,
                reasons=reasons,
            )
        )
    approved = [v.key for v in verdicts if v.passed]

    hmm = fit_hmm(y, 2)
    filtered = hmm_filter(y, hmm)
    regime = [
        RegimePoint(m, round(float(p), 4))
        for m, p in zip(sample.months, filtered[:, 0], strict=True)
    ]
    verdict = (
        "Passaram nos portões: " + ", ".join(v.label for v in verdicts if v.passed) + "."
        if approved
        else "Nenhum modelo passou nos portões: não há evidência de que regime ou risco "
        "condicional prevejam o mês seguinte melhor que a referência simples. É um resultado "
        "válido, e a camada B segue sem eles."
    )
    warnings = [
        f"{trials} tentativas de modelo registradas no laboratório até agora: cada uma "
        "aumenta a régua do Sharpe deflacionado.",
        "A probabilidade de regime de estresse descreve o passado com o modelo de 2 estados; "
        "não é previsão de queda.",
    ]
    return LabResult(
        months=int(y.size),
        first_forecast=sample.months[start],
        last_forecast=sample.months[-1],
        trials=trials,
        pbo=pbo,
        loss_probability=loss,
        models=verdicts,
        approved=approved,
        regime=regime,
        regime_means=[round(float(m), 6) for m in hmm.means],
        verdict=verdict,
        warnings=warnings,
    )
