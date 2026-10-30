"""Layer A of the price forecast (Phase 42.1): market and class, Bayesian.

The asset is modelled against its ARCA class exactly as a simulation candidate (Phase 33.7):
monthly total return in excess of the CDI = α + β · class excess + ε, with β ~ N(1, 0.5²),
α shrunk toward 0 by the spread of the class alphas (empirical Bayes) and ε resampled in blocks
from the asset's own residuals. The class paths are the calibrated mixture of the projection,
so an asset forecast agrees with the portfolio one.

The model works on total return (dividends reinvested); the price is the total return less the
dividend yield the asset's own history shows (`dividend_drag`). Each horizon keeps a grid of
price quantiles, so any "chance of passing R$ X" is read from it; the stored chances (up, fall
of 20%) carry a credibility interval for the parameter and sampling uncertainty.

Nothing here is a price target: the output is a distribution, with its confidence measured by
`domain.forecast.calibration`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import numpy as np

from domain.simulation.bayes import credible_interval
from domain.simulation.candidates import FactorFit
from domain.simulation.scenarios import stationary_bootstrap_indices

MODEL_VERSION = "42.1.0"
HORIZONS: tuple[int, ...] = (3, 6, 12, 24)  # months (decision 42.0-1)
QUANTILE_LEVELS: tuple[float, ...] = tuple(round(i / 100, 2) for i in range(1, 100))
FALL_THRESHOLD = 0.20
DEFAULT_PATHS = 4000
MEAN_BLOCK_MONTHS = 6.0


@dataclass(frozen=True)
class Probability:
    value: float
    low: float
    high: float


@dataclass(frozen=True)
class HorizonForecast:
    months: int
    # Price quantiles at QUANTILE_LEVELS (99 values); p5..p95 are read from them.
    price_quantiles: list[float]
    total_return_p50: float
    up: Probability  # price above today's
    fall_20: Probability  # price at least 20% below today's

    def price_at(self, level: float) -> float:
        return quantile_value(self.price_quantiles, level)


@dataclass(frozen=True)
class Driver:
    """One part of the expected annual total return (the centre of the distribution)."""

    key: str  # MARKET | OWN | VALUATION | EVENTS
    label: str
    annual: float | None  # None when the layer did not enter (not computed or did not pass)
    note: str = ""


@dataclass(frozen=True)
class PriceForecast:
    ticker: str
    as_of: date
    price_now: float
    months_used: int
    beta: float
    alpha_annual: float
    shrinkage: float
    dividend_yield_annual: float
    expected_total_return_annual: float
    horizons: list[HorizonForecast]
    drivers: list[Driver]
    paths: int
    model_version: str = MODEL_VERSION
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["as_of"] = self.as_of.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PriceForecast:
        horizons = [
            HorizonForecast(
                months=h["months"],
                price_quantiles=list(h["price_quantiles"]),
                total_return_p50=h["total_return_p50"],
                up=Probability(**h["up"]),
                fall_20=Probability(**h["fall_20"]),
            )
            for h in data["horizons"]
        ]
        return cls(
            ticker=data["ticker"],
            as_of=date.fromisoformat(data["as_of"]),
            price_now=data["price_now"],
            months_used=data["months_used"],
            beta=data["beta"],
            alpha_annual=data["alpha_annual"],
            shrinkage=data["shrinkage"],
            dividend_yield_annual=data["dividend_yield_annual"],
            expected_total_return_annual=data["expected_total_return_annual"],
            horizons=horizons,
            drivers=[Driver(**d) for d in data["drivers"]],
            paths=data["paths"],
            model_version=data.get("model_version", MODEL_VERSION),
            warnings=list(data.get("warnings", [])),
        )


def quantile_value(grid: Sequence[float], level: float) -> float:
    """The price at a quantile level, interpolated on the stored grid."""
    levels = np.array(QUANTILE_LEVELS)
    return float(np.interp(min(max(level, levels[0]), levels[-1]), levels, np.asarray(grid)))


def chance_above(grid: Sequence[float], price: float) -> float:
    """P(price > `price`) read from the quantile grid (0.5% to 99.5% at the ends)."""
    values = np.asarray(grid, dtype=float)
    if price <= values[0]:
        return 0.995
    if price >= values[-1]:
        return 0.005
    level = float(np.interp(price, values, np.array(QUANTILE_LEVELS)))
    return round(1.0 - level, 4)


def dividend_drag(total_return: Sequence[float], price: Sequence[float]) -> float:
    """Average monthly gap between total return and price growth (the dividend yield, ≥ 0)."""
    tr = np.asarray(total_return, dtype=float)
    px = np.asarray(price, dtype=float)
    n = min(tr.size, px.size)
    if n < 13:
        return 0.0
    tr, px = tr[-n:], px[-n:]
    gap = np.log(tr[1:] / tr[:-1]) - np.log(px[1:] / px[:-1])
    gap = gap[np.isfinite(gap)]
    return float(max(np.mean(gap), 0.0)) if gap.size else 0.0


def _probability(hits: np.ndarray) -> Probability:
    k, n = float(hits.sum()), float(hits.size)
    low, high = credible_interval(k, n)
    value = round(k / n, 4)
    # At 0 or n hits the Beta interval sits just inside (0, 1); keep the share in it.
    return Probability(value, min(low, value), max(high, value))


def forecast_asset(
    fit: FactorFit,
    class_excess: np.ndarray,
    *,
    cdi_monthly: float,
    price_now: float,
    drag_monthly: float,
    as_of: date,
    seed: int,
    horizons: Sequence[int] = HORIZONS,
    mean_block: float = MEAN_BLOCK_MONTHS,
    class_expected_excess_monthly: float = 0.0,
    valuation_note: str | None = None,
) -> PriceForecast:
    """Price paths of one asset on the class paths `class_excess` (paths, months ≥ max horizon)."""
    rng = np.random.default_rng(seed)
    paths, months = class_excess.shape
    horizon_max = max(horizons)
    if months < horizon_max:
        raise ValueError(f"class paths cover {months} months; {horizon_max} are needed")
    alpha = rng.normal(fit.alpha_post, fit.alpha_post_sd, paths)[:, None]
    beta = rng.normal(fit.beta_post, fit.beta_post_sd, paths)[:, None]
    idx = stationary_bootstrap_indices(fit.residuals.size, horizon_max, paths, mean_block, rng)
    excess = alpha + beta * class_excess[:, :horizon_max] + fit.residuals[idx]
    excess = np.maximum(excess, -0.99)
    total = (1.0 + excess) * (1.0 + cdi_monthly)
    tr_growth = np.cumprod(total, axis=1)  # (paths, months)
    price_growth = tr_growth * (1.0 - drag_monthly) ** np.arange(1, horizon_max + 1)

    out: list[HorizonForecast] = []
    for h in horizons:
        prices = price_now * price_growth[:, h - 1]
        out.append(
            HorizonForecast(
                months=h,
                price_quantiles=[round(float(v), 4) for v in np.quantile(prices, QUANTILE_LEVELS)],
                total_return_p50=round(float(np.median(tr_growth[:, h - 1])) - 1.0, 4),
                up=_probability(prices > price_now),
                fall_20=_probability(prices <= price_now * (1.0 - FALL_THRESHOLD)),
            )
        )

    market_annual = (1.0 + cdi_monthly) ** 12 * (
        1.0 + fit.beta_post * class_expected_excess_monthly
    ) ** 12 - 1.0
    # α_post = w·α̂ + (1 - w)·μ: the part pulled to μ is the valuation signal (42.3).
    valuation_monthly = fit.shrinkage * fit.alpha_prior_mean
    own_annual = (1.0 + fit.alpha_post - valuation_monthly) ** 12 - 1.0
    valuation_annual = (1.0 + valuation_monthly) ** 12 - 1.0
    expected = (1.0 + market_annual) * (1.0 + fit.alpha_post) ** 12 - 1.0
    drivers = [
        Driver(
            "MARKET",
            "Mercado e classe",
            round(market_annual, 4),
            f"CDI mais β {fit.beta_post:.2f} vezes o prêmio esperado da classe.",
        ),
        Driver(
            "OWN",
            "Desempenho próprio do ativo (α)",
            round(own_annual, 4),
            f"Encolhido em {fit.shrinkage:.0%} pela dispersão da classe, para não premiar sorte.",
        ),
        Driver(
            "VALUATION",
            "Valuation (balanços da CVM)",
            round(valuation_annual, 4) if fit.alpha_prior_mean else None,
            valuation_note or "Sem sinal de valuation para este ativo.",
        ),
        Driver("EVENTS", "Eventos recentes da CVM", None, "Entra na Fase 42.5."),
    ]
    warnings = []
    if fit.months < 60:
        warnings.append(
            f"Histórico de {fit.months} meses: a faixa reflete mais a classe do que o ativo."
        )
    return PriceForecast(
        ticker=fit.ticker,
        as_of=as_of,
        price_now=round(price_now, 4),
        months_used=fit.months,
        beta=round(fit.beta_post, 4),
        alpha_annual=round(own_annual, 4),
        shrinkage=fit.shrinkage,
        dividend_yield_annual=round(1.0 - (1.0 - drag_monthly) ** 12, 4),
        expected_total_return_annual=round(expected, 4),
        horizons=out,
        drivers=drivers,
        paths=paths,
        warnings=warnings,
    )
