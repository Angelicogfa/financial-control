"""How far the price forecasts can be trusted (Phase 42.1): a rolling-origin backtest.

At each origin month the layer A model is fitted with the data up to that month only (the
class spread τ included), projects the next `horizon` months on class paths resampled from
the class history up to then, and is compared with what happened:

- coverage of the 50% and 90% bands of the cumulative excess return over the CDI;
- the mean PIT (0.5 = no bias in the centre);
- the Brier score of the chance of beating the CDI, against the 50/50 reference.

Origins overlap (a 12-month horizon every 3 months), so the effective number of windows
divides the count by horizon / step; the seal uses it, as the projection calibration does.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

import numpy as np

from domain.shared.enums import ArcaClass
from domain.simulation.candidates import (
    MIN_HISTORY_MONTHS,
    FactorFit,
    class_tau,
    ols_fit,
    shrink,
)
from domain.simulation.scenarios import CLASS_ORDER, ClassSample, stationary_bootstrap_indices

HORIZON_MONTHS = 12
STEP_MONTHS = 3
MIN_TRAIN_MONTHS = 60
CALIBRATION_PATHS = 600
MEAN_BLOCK_MONTHS = 6.0


@dataclass(frozen=True)
class ForecastCalibration:
    as_of: date
    horizon_months: int
    windows: int  # asset-origin pairs scored
    effective_windows: float
    assets: int
    coverage_50: float
    coverage_90: float
    mean_pit: float
    brier: float  # chance of beating the CDI
    brier_reference: float  # always 50%
    first_origin: date | None
    last_origin: date | None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["as_of"] = self.as_of.isoformat()
        data["first_origin"] = self.first_origin.isoformat() if self.first_origin else None
        data["last_origin"] = self.last_origin.isoformat() if self.last_origin else None
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ForecastCalibration:
        payload = dict(data)
        for key in ("as_of", "first_origin", "last_origin"):
            if payload.get(key):
                payload[key] = date.fromisoformat(payload[key])
        return cls(**payload)


def calibrate(
    excess_by_asset: Mapping[str, tuple[ArcaClass, np.ndarray, np.ndarray]],
    sample: ClassSample,
    *,
    as_of: date,
    seed: int,
    horizon: int = HORIZON_MONTHS,
    step: int = STEP_MONTHS,
    min_train: int = MIN_TRAIN_MONTHS,
    paths: int = CALIBRATION_PATHS,
) -> ForecastCalibration | None:
    """Score the layer A forecasts of every asset at every origin; None without any window."""
    rng = np.random.default_rng(seed)
    total = sample.size
    pits: list[float] = []
    hits_50: list[bool] = []
    hits_90: list[bool] = []
    briers: list[float] = []
    assets_scored: set[str] = set()
    origins: list[int] = []
    for origin in range(min_train, total - horizon + 1, step):
        fits: dict[str, FactorFit] = {}
        for ticker, (cls, excess, mask) in excess_by_asset.items():
            if cls not in sample.classes or cls == ArcaClass.CAIXA:
                continue
            train = mask[:origin]
            if train.sum() < MIN_HISTORY_MONTHS:
                continue
            k = CLASS_ORDER.index(cls)
            a, a_se, b, b_se, resid = ols_fit(
                excess[:origin][train], sample.excess[:origin, k][train]
            )
            fits[ticker] = FactorFit(ticker, cls, int(train.sum()), a, a_se, b, b_se, resid)
        if not fits:
            continue
        taus = {
            cls: class_tau([f for f in fits.values() if f.arca_class == cls])
            for cls in {f.arca_class for f in fits.values()}
        }
        idx = stationary_bootstrap_indices(origin, horizon, paths, MEAN_BLOCK_MONTHS, rng)
        scored = False
        for ticker, raw in fits.items():
            _cls, excess, mask = excess_by_asset[ticker]
            future = mask[origin : origin + horizon]
            if not future.all():
                continue
            fit = shrink(raw, taus[raw.arca_class])
            k = CLASS_ORDER.index(fit.arca_class)
            class_paths = sample.excess[:origin, k][idx]  # (paths, horizon)
            alpha = rng.normal(fit.alpha_post, fit.alpha_post_sd, paths)[:, None]
            beta = rng.normal(fit.beta_post, fit.beta_post_sd, paths)[:, None]
            r_idx = stationary_bootstrap_indices(
                fit.residuals.size, horizon, paths, MEAN_BLOCK_MONTHS, rng
            )
            simulated = np.prod(
                1.0 + np.maximum(alpha + beta * class_paths + fit.residuals[r_idx], -0.99), axis=1
            )
            realized = float(np.prod(1.0 + excess[origin : origin + horizon]))
            pit = float(np.mean(simulated < realized))
            pits.append(pit)
            hits_50.append(0.25 < pit <= 0.75)
            hits_90.append(0.05 < pit <= 0.95)
            p_beat = float(np.mean(simulated > 1.0))
            briers.append((p_beat - (1.0 if realized > 1.0 else 0.0)) ** 2)
            assets_scored.add(ticker)
            scored = True
        if scored:
            origins.append(origin)
    if not pits:
        return None
    windows = len(pits)
    return ForecastCalibration(
        as_of=as_of,
        horizon_months=horizon,
        windows=windows,
        effective_windows=round(windows * step / horizon, 1),
        assets=len(assets_scored),
        coverage_50=round(float(np.mean(hits_50)), 4),
        coverage_90=round(float(np.mean(hits_90)), 4),
        mean_pit=round(float(np.mean(pits)), 4),
        brier=round(float(np.mean(briers)), 4),
        brier_reference=0.25,
        first_origin=sample.months[origins[0] - 1] if origins else None,
        last_origin=sample.months[origins[-1] - 1] if origins else None,
    )


def calibration_seal_inputs(
    calibration: ForecastCalibration | None,
) -> tuple[float | None, float]:
    """(coverage of the 90% band, effective windows) for `confidence_seal`."""
    if calibration is None:
        return None, 0.0
    return calibration.coverage_90, calibration.effective_windows
