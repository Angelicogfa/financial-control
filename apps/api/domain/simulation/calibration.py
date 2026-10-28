"""Walk-forward calibration of the scenario generators (Phase 33.6, design 6.4, risk R19).

At every past month-end origin with enough history before it, each generator is rebuilt
from the data up to that origin only and forecasts the next 12 months of the model
portfolio (the policy targets, rebalanced monthly), as the excess over the CDI. The forecast
is compared with what happened:

- PIT: position of the realized value in the forecast (uniform when calibrated);
- coverage of the 90% interval, with a Beta posterior over an effective number of windows
  (monthly origins overlap: 12 consecutive windows share most months, n_eff = n / 12);
- Brier score of two events: losing more than 10% in 12 months and beating the CDI;
- log score of the realized value under the forecast density (Gaussian kernel).

Stacking weights of the generators maximize the log score of their mixture (design 6.4.4);
the mixture is then scored like the others. The total return uses the CDI that actually
happened: the generators forecast premiums over the rates, which are a scenario input.
A short history gives an inconclusive result, and that is reported as such (6.4.5).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from enum import StrEnum

import numpy as np

from domain.shared.enums import ArcaClass
from domain.simulation.bayes import credible_interval, stacking_weights
from domain.simulation.engine import SimulationTimeout
from domain.simulation.generators import (
    GENERATOR_LABELS,
    Generator,
    draw_excess,
    sample_posterior,
)
from domain.simulation.scenarios import CLASS_ORDER, ClassSample, InsufficientHistory

HORIZON = 12
MIN_TRAIN_MONTHS = 60
PATHS_PER_ORIGIN = 400
NOMINAL_COVERAGE = 0.90
LOSS_THRESHOLD = -0.10
PIT_BINS = 10
# Fewer effective windows, or a wider coverage interval, cannot tell good from bad.
MIN_EFFECTIVE_WINDOWS = 8.0
MAX_INTERVAL_WIDTH = 0.35
STACKED = "STACKED"


class CalibrationStatus(StrEnum):
    CALIBRATED = "CALIBRATED"
    MISCALIBRATED = "MISCALIBRATED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class GeneratorCalibration:
    key: str
    label: str
    weight: float
    windows: int
    effective_windows: float
    coverage: float
    coverage_low: float
    coverage_high: float
    status: CalibrationStatus
    pit_histogram: list[int]
    mean_pit: float
    brier_loss: float
    brier_beat_cdi: float
    log_score: float


@dataclass(frozen=True)
class OriginForecast:
    """One origin: what happened and each generator's 5-50-95% forecast and PIT."""

    origin: date
    realized: float  # 12-month total return of the model portfolio
    forecasts: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class CalibrationResult:
    horizon_months: int
    windows: int
    effective_windows: float
    first_origin: date
    last_origin: date
    classes: tuple[ArcaClass, ...]
    targets: dict[ArcaClass, float]
    weights: dict[str, float]
    generators: list[GeneratorCalibration]
    origins: list[OriginForecast]
    warnings: list[str]


def _log_density(samples: np.ndarray, value: float) -> float:
    """Log of a Gaussian kernel density (Silverman bandwidth) of `samples` at `value`."""
    n = samples.size
    std = float(samples.std(ddof=1))
    iqr = float(np.subtract(*np.percentile(samples, [75, 25])))
    spread = min(std, iqr / 1.349) if iqr > 0 else std
    h = max(0.9 * spread * n ** (-0.2), 1e-6)
    z = (value - samples) / h
    dens = float(np.exp(-0.5 * z * z).sum() / (n * h * math.sqrt(2.0 * math.pi)))
    return math.log(max(dens, 1e-300))


def _status(low: float, high: float, effective: float) -> CalibrationStatus:
    if effective < MIN_EFFECTIVE_WINDOWS or high - low > MAX_INTERVAL_WIDTH:
        return CalibrationStatus.INCONCLUSIVE
    if not low <= NOMINAL_COVERAGE <= high:
        return CalibrationStatus.MISCALIBRATED
    return CalibrationStatus.CALIBRATED


def _score(
    key: str,
    weight: float,
    forecasts: list[np.ndarray],
    realized: np.ndarray,
    cdi_factor: np.ndarray,
) -> tuple[GeneratorCalibration, list[float], np.ndarray]:
    """Scores of one generator over all origins; also its PITs and predictive densities."""
    pits, covered, log_dens, brier_loss, brier_beat = [], [], [], [], []
    for sims, real, cdi in zip(forecasts, realized, cdi_factor, strict=True):
        total = sims * cdi - 1.0
        real_total = real * cdi - 1.0
        q5, q95 = np.percentile(sims, [5, 95])
        pits.append(float((sims <= real).mean()))
        covered.append(bool(q5 <= real <= q95))
        log_dens.append(_log_density(np.log(sims), math.log(real)))
        p_loss = float((total < LOSS_THRESHOLD).mean())
        p_beat = float((sims > 1.0).mean())
        brier_loss.append((p_loss - float(real_total < LOSS_THRESHOLD)) ** 2)
        brier_beat.append((p_beat - float(real > 1.0)) ** 2)
    n = len(pits)
    effective = n / HORIZON
    rate = float(np.mean(covered))
    low, high = credible_interval(rate * effective, effective)
    hist = np.histogram(pits, bins=PIT_BINS, range=(0.0, 1.0))[0]
    return (
        GeneratorCalibration(
            key=key,
            label=GENERATOR_LABELS.get(key, key),
            weight=round(weight, 4),
            windows=n,
            effective_windows=round(effective, 2),
            coverage=round(rate, 4),
            coverage_low=low,
            coverage_high=high,
            status=_status(low, high, effective),
            pit_histogram=[int(v) for v in hist],
            mean_pit=round(float(np.mean(pits)), 4),
            brier_loss=round(float(np.mean(brier_loss)), 4),
            brier_beat_cdi=round(float(np.mean(brier_beat)), 4),
            log_score=round(float(np.mean(log_dens)), 4),
        ),
        pits,
        np.exp(np.array(log_dens)),
    )


def calibrate(
    sample: ClassSample,
    targets: Mapping[ArcaClass, float],
    *,
    seed: int,
    mean_block: float = 12.0,
    paths: int = PATHS_PER_ORIGIN,
    min_train: int = MIN_TRAIN_MONTHS,
    deadline: Callable[[], bool] | None = None,
) -> CalibrationResult:
    """Forecast each 12-month window from the data before it and score the generators."""
    t_total = sample.size
    origins = list(range(min_train, t_total - HORIZON + 1))
    if not origins:
        raise InsufficientHistory(
            f"A calibração precisa de {min_train + HORIZON} meses de histórico comum; há {t_total}."
        )
    weights_by_class = np.array([targets.get(c, 0.0) for c in CLASS_ORDER])
    weights_by_class = weights_by_class / weights_by_class.sum()

    def growth(excess: np.ndarray) -> np.ndarray:
        """12-month growth over the CDI of the model portfolio, rebalanced monthly."""
        return np.prod(1.0 + excess @ weights_by_class, axis=-1)

    realized = np.array([growth(sample.excess[o : o + HORIZON]) for o in origins])
    cdi_factor = np.array([np.prod(1.0 + sample.cdi[o : o + HORIZON]) for o in origins])

    sims: dict[str, list[np.ndarray]] = {g.value: [] for g in Generator}
    for i, o in enumerate(origins):
        if deadline is not None and deadline():
            raise SimulationTimeout(f"calibration stopped at origin {i}")
        train = ClassSample(
            months=sample.months[:o],
            excess=sample.excess[:o],
            cdi=sample.cdi[:o],
            classes=sample.classes,
        )
        posterior = sample_posterior(train)
        for j, g in enumerate(Generator):
            rng = np.random.default_rng([seed, o, j])
            drawn = draw_excess(
                train, g, paths, HORIZON, mean_block=mean_block, rng=rng, posterior=posterior
            )
            sims[g.value].append(growth(drawn))

    scored = {g: _score(g, 0.0, sims[g], realized, cdi_factor) for g in sims}
    densities = np.column_stack([scored[g][2] for g in sims])
    weights = dict(
        zip(sims, (round(float(w), 4) for w in stacking_weights(densities)), strict=True)
    )

    # The mixture, scored like a generator: each origin pools its share of every generator.
    mixed: list[np.ndarray] = []
    for i in range(len(origins)):
        parts = [sims[g][i][: int(round(weights[g] * paths))] for g in sims]
        mixed.append(np.concatenate([p for p in parts if p.size]))
    stacked, stacked_pits, _ = _score(STACKED, 1.0, mixed, realized, cdi_factor)

    generators = [replace(scored[g][0], weight=weights[g]) for g in sims] + [stacked]

    forecasts: list[OriginForecast] = []
    for i, o in enumerate(origins):
        row: dict[str, dict[str, float]] = {}
        for g, values in [*((g, sims[g][i]) for g in sims), (STACKED, mixed[i])]:
            total = values * cdi_factor[i] - 1.0
            q5, q50, q95 = np.percentile(total, [5, 50, 95])
            row[g] = {
                "p5": round(float(q5), 4),
                "p50": round(float(q50), 4),
                "p95": round(float(q95), 4),
            }
        row[STACKED]["pit"] = round(stacked_pits[i], 4)
        forecasts.append(
            OriginForecast(
                origin=sample.months[o - 1],
                realized=round(float(realized[i] * cdi_factor[i] - 1.0), 4),
                forecasts=row,
            )
        )

    effective = len(origins) / HORIZON
    warnings = [
        "As janelas de 12 meses se sobrepõem: "
        f"{len(origins)} origens mensais valem cerca de {effective:.0f} janelas independentes.",
        "A calibração testa os prêmios sobre o CDI; os juros entram como foram de fato.",
        "Cada gerador só vê o passado de cada origem, mas os pesos da combinação são "
        "estimados com todas as origens: a linha da combinação é um pouco otimista.",
    ]
    if any(g.status == CalibrationStatus.INCONCLUSIVE for g in generators):
        warnings.append(
            "Calibração inconclusiva: o histórico não basta para separar um gerador bem "
            "calibrado de um mal calibrado (risco R19). É um resultado válido, não um erro."
        )
    if any(g.status == CalibrationStatus.MISCALIBRATED for g in generators):
        warnings.append(
            "Há gerador mal calibrado: a cobertura de 90% fica fora do intervalo de "
            "credibilidade. Ele continua na mistura com o peso que o stacking deu (só aviso)."
        )
    return CalibrationResult(
        horizon_months=HORIZON,
        windows=len(origins),
        effective_windows=round(effective, 2),
        first_origin=sample.months[origins[0] - 1],
        last_origin=sample.months[origins[-1] - 1],
        classes=sample.classes,
        targets={c: float(weights_by_class[CLASS_ORDER.index(c)]) for c in CLASS_ORDER},
        weights=weights,
        generators=generators,
        origins=forecasts,
        warnings=warnings,
    )
