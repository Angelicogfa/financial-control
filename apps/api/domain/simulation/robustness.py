"""Robustness of a backtest (Phase 33.4, design sections 1.3, 8.1 and risks R3/R4).

- Historical crises: the strategy and each benchmark measured inside fixed windows (2008,
  2015-16, Joesley Day, Covid, the 2021-22 rate hikes), with the monthly time-weighted return
  (contributions removed) and the drawdown inside the window.
- Synthetic shocks: an instant first-order move per ARCA class applied to the final allocation
  (no second-order effects such as a rate rise also hitting stocks).
- Rule variants: the same run with other bands and with/without rebalancing. Every variant is
  counted (trials, risk R3) and the whole distribution is shown, not only the best one; the
  last `HOLDOUT_MONTHS` are reported apart because they are reserved for validation.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

import numpy as np

from domain.policy.services.policy import ArcaPolicy, InvestmentPolicy
from domain.shared.enums import ArcaClass
from domain.simulation.engine import BacktestPoint
from domain.simulation.validation import ValidationReport, validate_configurations

HOLDOUT_MONTHS = 36
# Fewer months than this: annual figures and the variant comparison are only indicative.
MIN_SAMPLE_MONTHS = 60
VARIANT_BANDS: tuple[float, ...] = (0.0, 5.0, 10.0, 20.0)
VARIANT_PREFIX = "variant:"


@dataclass(frozen=True)
class Crisis:
    key: str
    label: str
    start: date
    end: date


HISTORICAL_CRISES: tuple[Crisis, ...] = (
    Crisis("GFC_2008", "Crise de 2008", date(2008, 9, 1), date(2009, 2, 28)),
    Crisis("RECESSION_2015", "Recessão de 2015–16", date(2015, 1, 1), date(2016, 12, 31)),
    Crisis("JOESLEY_2017", "Joesley Day", date(2017, 5, 1), date(2017, 5, 31)),
    Crisis("COVID_2020", "Covid", date(2020, 2, 1), date(2020, 3, 31)),
    Crisis("RATES_2021", "Alta de juros de 2021–22", date(2021, 1, 1), date(2022, 12, 31)),
)


@dataclass(frozen=True)
class WindowOutcome:
    """Time-weighted return and drawdown of one series inside a window."""

    covered: bool
    months: int = 0
    return_rate: float | None = None  # fraction, contributions removed
    max_drawdown: float | None = None  # negative fraction


def monthly_returns(points: Sequence[BacktestPoint]) -> list[tuple[date, float]]:
    """Return of each month with that month's contribution removed (Modified Dietz at the end)."""
    out: list[tuple[date, float]] = []
    for prev, cur in zip(points, points[1:], strict=False):
        if prev.market_value > 0:
            out.append((cur.day, (cur.market_value - cur.contribution) / prev.market_value - 1.0))
    return out


def window_outcome(points: Sequence[BacktestPoint], start: date, end: date) -> WindowOutcome:
    """Measure a window; it counts only when the series already existed before it began."""
    # Month-end steps: the window's last month only needs to be reached, not its last day.
    if not points or points[0].day >= start or points[-1].day < date(end.year, end.month, 1):
        return WindowOutcome(covered=False)
    returns = [r for d, r in monthly_returns(points) if start <= d <= end]
    if not returns:
        return WindowOutcome(covered=False)
    growth = peak = 1.0
    worst = 0.0
    for r in returns:
        growth *= 1.0 + r
        peak = max(peak, growth)
        worst = min(worst, growth / peak - 1.0)
    return WindowOutcome(
        covered=True,
        months=len(returns),
        return_rate=round(growth - 1.0, 6),
        max_drawdown=round(worst, 6),
    )


def crisis_outcomes(points: Sequence[BacktestPoint]) -> dict[str, WindowOutcome]:
    return {c.key: window_outcome(points, c.start, c.end) for c in HISTORICAL_CRISES}


@dataclass(frozen=True)
class Shock:
    key: str
    label: str
    # Instant move per class (fraction); `real` deflates the whole portfolio (inflation).
    moves: Mapping[ArcaClass, float] = field(default_factory=dict)
    real: float | None = None
    note: str = ""


SYNTHETIC_SHOCKS: tuple[Shock, ...] = (
    Shock("EQUITY_MINUS_30", "Ações −30% num mês", {ArcaClass.ACOES: -0.30}),
    Shock(
        "CDI_PLUS_5",
        "CDI +5 p.p. por 12 meses",
        {ArcaClass.CAIXA: 0.05},
        note="Só o rendimento extra do caixa; o efeito dos juros sobre ações e FIIs não entra.",
    ),
    Shock(
        "IPCA_12",
        "IPCA de 12% ao ano",
        real=1.0 / 1.12 - 1.0,
        note="Perda de poder de compra em 12 meses, em valores de hoje.",
    ),
    Shock("FX_PLUS_40", "Dólar +40%", {ArcaClass.ATIVOS_INTERNACIONAIS: 0.40}),
    Shock(
        "REAL_ESTATE_MINUS_20",
        "FIIs −20% (DY constante)",
        {ArcaClass.REAL_ESTATE: -0.20},
        note="Preço cai, rendimento mensal mantido.",
    ),
)


@dataclass(frozen=True)
class ShockOutcome:
    key: str
    label: str
    before: float
    after: float
    change: float
    change_rate: float
    by_class: dict[ArcaClass, float]
    note: str = ""


def apply_shock(by_class: Mapping[ArcaClass, float], cash: float, shock: Shock) -> ShockOutcome:
    """First-order effect of a shock on the allocation (uninvested cash counts as CAIXA)."""
    values = dict(by_class)
    values[ArcaClass.CAIXA] = values.get(ArcaClass.CAIXA, 0.0) + cash
    before = sum(values.values())
    after_by_class = {c: v * (1.0 + shock.moves.get(c, 0.0)) for c, v in values.items()}
    if shock.real is not None:
        after_by_class = {c: v * (1.0 + shock.real) for c, v in after_by_class.items()}
    after = sum(after_by_class.values())
    return ShockOutcome(
        key=shock.key,
        label=shock.label,
        before=round(before, 2),
        after=round(after, 2),
        change=round(after - before, 2),
        change_rate=round(after / before - 1.0, 6) if before > 0 else 0.0,
        by_class={c: round(v, 2) for c, v in after_by_class.items()},
        note=shock.note,
    )


@dataclass(frozen=True)
class RuleVariant:
    key: str
    label: str
    band_pct: float
    rebalance: bool


def rule_variants() -> list[RuleVariant]:
    """Every band width with and without monthly rebalancing."""
    return [
        RuleVariant(
            key=f"{VARIANT_PREFIX}band{band:g}:{'rebalance' if rebalance else 'hold'}",
            label=f"Banda {band:g} p.p., {'rebalanceando' if rebalance else 'só aportando'}",
            band_pct=band,
            rebalance=rebalance,
        )
        for band in VARIANT_BANDS
        for rebalance in (False, True)
    ]


def with_band(policy: InvestmentPolicy, band_pct: float) -> InvestmentPolicy:
    """The policy with the same band on every class (targets and strategies kept)."""
    arca = ArcaPolicy({c: replace(p, band_pct=band_pct) for c, p in policy.arca.classes.items()})
    return replace(policy, arca=arca)


def holdout_start(end: date, months: int = HOLDOUT_MONTHS) -> date:
    """First day of the reserved window: the last `months` months up to `end`, inclusive."""
    month = end.month - months + 1
    year = end.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return date(year, month, 1)


@dataclass(frozen=True)
class Distribution:
    count: int
    minimum: float | None = None
    median: float | None = None
    maximum: float | None = None


def distribution(values: Sequence[float | None]) -> Distribution:
    known = sorted(v for v in values if v is not None)
    if not known:
        return Distribution(count=0)
    return Distribution(
        count=len(known),
        minimum=round(known[0], 6),
        median=round(statistics.median(known), 6),
        maximum=round(known[-1], 6),
    )


def sample_warnings(
    points: Sequence[BacktestPoint], crises: Mapping[str, WindowOutcome]
) -> list[str]:
    """What the sample cannot support (risk R4); always at least the structural warning."""
    warnings = [
        "O histórico brasileiro tem cerca de 20 anos de dados limpos e poucos ciclos; o "
        "resultado descreve o passado e não garante o futuro."
    ]
    months = max(len(points) - 1, 0)
    if months < MIN_SAMPLE_MONTHS:
        warnings.append(
            f"Amostra curta: {months} meses (menos de {MIN_SAMPLE_MONTHS}). Números anuais e a "
            "comparação entre variantes são só indicativos."
        )
    missing = [
        c.label for c in HISTORICAL_CRISES if not (c.key in crises and crises[c.key].covered)
    ]
    if missing:
        warnings.append("Crises fora do período simulado: " + ", ".join(missing) + ".")
    return warnings


def points_from_stored(rows: Sequence[Mapping[str, Any]]) -> list[BacktestPoint]:
    """Monthly points as stored in `simulation_results.points`."""
    return [
        BacktestPoint(
            day=date.fromisoformat(r["day"]),
            contribution=float(r["contribution"]),
            contributed=float(r["contributed"]),
            market_value=float(r["market_value"]),
            cash=float(r["cash"]),
            fees=float(r["fees"]),
            taxes=float(r.get("taxes", 0.0)),
            by_class={ArcaClass(k): float(v) for k, v in (r.get("by_class") or {}).items()},
        )
        for r in rows
    ]


# Fewer aligned months than this cannot support the overfitting statistics (Phase 33.8).
MIN_VALIDATION_MONTHS = 24


def variant_validation(
    points: Mapping[str, Sequence[BacktestPoint]],
    variant_keys: Sequence[str],
    *,
    reference_key: str,
    cdi_key: str | None,
    trials_total: int,
    seed: int = 0,
) -> ValidationReport | None:
    """Phase 33.8 on the rule variants: deflated Sharpe of the best (all trials counted),
    PBO of the set and the Bayesian gate of the best against the current rule.

    Returns are monthly, contributions removed, in excess of the CDI when it was simulated.
    """
    keys = [k for k in variant_keys if points.get(k)]
    if len(keys) < 2 or not points.get(reference_key):
        return None
    series = {k: dict(monthly_returns(points[k])) for k in [*keys, reference_key]}
    cdi = dict(monthly_returns(points[cdi_key])) if cdi_key and points.get(cdi_key) else None
    common = set.intersection(*(set(v) for v in series.values()))
    if cdi is not None:
        common &= set(cdi)
    months = sorted(common)
    if len(months) < MIN_VALIDATION_MONTHS:
        return None

    def excess(key: str) -> np.ndarray:
        values = np.array([series[key][m] for m in months])
        return values - np.array([cdi[m] for m in months]) if cdi is not None else values

    return validate_configurations(
        {k: excess(k) for k in keys},
        reference=excess(reference_key),
        n_trials=max(trials_total, len(keys)),
        seed=seed,
    )
