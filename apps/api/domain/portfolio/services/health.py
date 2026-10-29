"""Portfolio health diagnosis in seven pillars (Phase 29, MARKET_ANALYSIS §7.3).

Every check returns ok / atenção / crítico (or "dados insuficientes" when its minimum window
is not met), the measured value, the limits of the versioned policy, an explanation and the
suggested action. A pillar takes the state of its worst check and the report lists the
pillars worst first, so a critical check is never diluted by an average.

The engine is pure: the application service loads positions, return series and statements
and hands them over as `HealthInputs`.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from enum import StrEnum

from domain.policy.services.allocation import BAND_ABOVE, BAND_WITHIN, ClassAllocation
from domain.policy.services.policy import HealthPolicy
from domain.portfolio.services.analytics import (
    annualized_volatility,
    cagr,
    conditional_var,
    cumulative_return,
    historical_var,
    sharpe_ratio,
)
from domain.portfolio.services.diversification import (
    Concentration,
    concentration,
    decompose_risk,
    estimate_covariance,
    sample_correlations,
    top_weight,
)
from domain.portfolio.services.risk_metrics import (
    ROLLING_WINDOW,
    STRESS_WINDOW,
    ConfidenceInterval,
    RollingPoint,
    StressResult,
    bootstrap_intervals,
    consistency_against,
    drawdown_state,
    historical_stress,
    information_ratio,
    omega_ratio,
    rolling_windows,
    tracking_error,
    ulcer_index,
    weighted_returns,
)
from domain.shared.enums import ARCA_LABELS, ArcaClass, AssetPurpose, AssetType
from domain.shared.text import plural

MIN_DRAWDOWN_OBSERVATIONS = 20
MIN_CONSISTENCY_MONTHS = 6
LOW_F_SCORE = 3
Z_DISTRESS = 1.1
UNKNOWN_SECTOR = "Não informado"

SOVEREIGN_TYPES = frozenset({AssetType.TREASURY, AssetType.CASH})
VARIABLE_INCOME_TYPES = frozenset(
    {
        AssetType.STOCK_BR,
        AssetType.ETF_BR,
        AssetType.FII,
        AssetType.BDR,
        AssetType.STOCK_INTL,
        AssetType.ETF_INTL,
        AssetType.REIT,
        AssetType.CRYPTO,
    }
)
# Funds that already spread over many sectors stay out of the sector check.
DIVERSIFIED_TYPES = frozenset({AssetType.ETF_BR, AssetType.ETF_INTL})


class HealthStatus(StrEnum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class HealthPillar(StrEnum):
    POLICY = "POLICY"
    CONCENTRATION = "CONCENTRATION"
    DIVERSIFICATION = "DIVERSIFICATION"
    RISK = "RISK"
    PERFORMANCE = "PERFORMANCE"
    QUALITY = "QUALITY"
    LIQUIDITY = "LIQUIDITY"


class HealthUnit(StrEnum):
    FRACTION = "FRACTION"
    RATIO = "RATIO"
    BRL = "BRL"
    MONTHS = "MONTHS"
    DAYS = "DAYS"
    COUNT = "COUNT"


PILLAR_TITLES: dict[HealthPillar, str] = {
    HealthPillar.POLICY: "Aderência à política",
    HealthPillar.CONCENTRATION: "Concentração",
    HealthPillar.DIVERSIFICATION: "Diversificação de risco",
    HealthPillar.RISK: "Risco",
    HealthPillar.PERFORMANCE: "Desempenho",
    HealthPillar.QUALITY: "Qualidade dos ativos",
    HealthPillar.LIQUIDITY: "Liquidez, renda e tributos",
}

_SEVERITY = {
    HealthStatus.CRITICAL: 0,
    HealthStatus.WARNING: 1,
    HealthStatus.INSUFFICIENT_DATA: 2,
    HealthStatus.OK: 3,
}
_PILLAR_ORDER = {p: i for i, p in enumerate(HealthPillar)}


@dataclass(frozen=True)
class Holding:
    """One valued position as the health engine needs it (weights come from `value_brl`)."""

    ticker: str
    name: str
    asset_type: AssetType
    arca_class: ArcaClass
    value_brl: float
    purpose: AssetPurpose = AssetPurpose.ARCA
    sector: str | None = None
    issuer: str | None = None
    fgc_covered: bool = False
    liquid_d2: bool = True
    maturity_date: date | None = None
    tax_exempt: bool = False
    eligible: bool = True
    checklist_ratio: float | None = None
    checklist_age_days: int | None = None
    checklist_stale: bool = False
    suspicious_data: bool = False
    f_score: int | None = None
    z_score: float | None = None


@dataclass(frozen=True)
class BracketLot:
    """An open fixed income lot whose income tax rate drops soon."""

    ticker: str
    start_date: date
    next_bracket_date: date
    days_to_next_bracket: int
    current_rate: float
    next_rate: float
    tax_saving_by_waiting: float


@dataclass(frozen=True)
class HealthInputs:
    as_of: date
    holdings: Sequence[Holding]
    allocations: Sequence[ClassAllocation] = ()
    earnings_12m_brl: float = 0.0
    portfolio_dates: Sequence[date] = ()
    portfolio_returns: Sequence[float] = ()
    benchmark_returns: Sequence[float | None] = ()
    cdi_returns: Sequence[float | None] = ()
    asset_dates: Sequence[date] = ()
    asset_returns: Mapping[str, Sequence[float | None]] = field(default_factory=dict)
    # What was dropped from the series as out of the possible range (Phase 32.4).
    asset_data_notes: Sequence[str] = ()
    portfolio_data_notes: Sequence[str] = ()
    class_returns: Mapping[ArcaClass, float] = field(default_factory=dict)
    class_out_of_band_days: Mapping[ArcaClass, int] = field(default_factory=dict)
    bracket_lots: Sequence[BracketLot] = ()
    annual_cdi_rate: float = 0.1075


@dataclass(frozen=True)
class HealthCheck:
    key: str
    title: str
    status: HealthStatus
    explanation: str
    action: str | None = None
    value: float | None = None
    unit: HealthUnit = HealthUnit.FRACTION
    warning_threshold: float | None = None
    critical_threshold: float | None = None
    observations: int | None = None
    min_observations: int | None = None
    # Enumerations shown one per line under the explanation (Phase 32.2).
    items: list[str] = field(default_factory=list)
    # The input series had data out of the possible range, dropped before computing (32.4).
    suspicious: str | None = None


@dataclass(frozen=True)
class PillarResult:
    pillar: HealthPillar
    title: str
    status: HealthStatus
    checks: list[HealthCheck]


@dataclass(frozen=True)
class ConcentrationBreakdown:
    dimension: str
    hhi: float
    effective_count: float
    weights: dict[str, float]


@dataclass(frozen=True)
class InstitutionExposure:
    issuer: str
    value_brl: float
    limit_brl: float
    usage: float


@dataclass(frozen=True)
class RiskShare:
    label: str
    weight: float
    risk_share: float


@dataclass(frozen=True)
class CorrelatedPair:
    first: str
    second: str
    correlation: float


@dataclass(frozen=True)
class DiversificationDetail:
    observations: int = 0
    shrinkage: float | None = None
    volatility: float | None = None
    diversification_ratio: float | None = None
    by_asset: list[RiskShare] = field(default_factory=list)
    by_class: list[RiskShare] = field(default_factory=list)
    correlated_pairs: list[CorrelatedPair] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RiskDetail:
    observations: int = 0
    volatility: float | None = None
    current_drawdown: float | None = None
    drawdown_periods: int | None = None
    peak_date: date | None = None
    ulcer_index: float | None = None
    var_95: float | None = None
    cvar_95: float | None = None
    stress: StressResult | None = None


@dataclass(frozen=True)
class PerformanceDetail:
    observations: int = 0
    cumulative_return: float | None = None
    cagr: float | None = None
    benchmark_return: float | None = None
    tracking_error: float | None = None
    information_ratio: float | None = None
    omega: float | None = None
    sharpe: float | None = None
    sharpe_interval: ConfidenceInterval | None = None
    cagr_interval: ConfidenceInterval | None = None
    cdi_consistency: float | None = None
    months_compared: int = 0
    rolling: list[RollingPoint] = field(default_factory=list)
    class_returns: dict[ArcaClass, float] = field(default_factory=dict)


@dataclass(frozen=True)
class HoldingQuality:
    ticker: str
    weight: float
    checklist_ratio: float | None
    stale: bool
    f_score: int | None
    z_score: float | None


@dataclass(frozen=True)
class Maturity:
    ticker: str
    maturity_date: date
    value_brl: float


@dataclass(frozen=True)
class LiquidityDetail:
    reserve_brl: float = 0.0
    reserve_months: float | None = None
    liquid_weight: float | None = None
    maturities_12m: list[Maturity] = field(default_factory=list)
    passive_income_12m_brl: float = 0.0
    exempt_weight: float | None = None
    bracket_lots: list[BracketLot] = field(default_factory=list)


@dataclass(frozen=True)
class HealthReport:
    as_of_date: date
    status: HealthStatus
    total_value_brl: float
    pillars: list[PillarResult]
    concentration: list[ConcentrationBreakdown] = field(default_factory=list)
    institutions: list[InstitutionExposure] = field(default_factory=list)
    diversification: DiversificationDetail = field(default_factory=DiversificationDetail)
    risk: RiskDetail = field(default_factory=RiskDetail)
    performance: PerformanceDetail = field(default_factory=PerformanceDetail)
    quality: list[HoldingQuality] = field(default_factory=list)
    liquidity: LiquidityDetail = field(default_factory=LiquidityDetail)


# --- formatting (user-facing texts are pt-BR) ---------------------------------------------


def _pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%".replace(".", ",")


def _num(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _brl(value: float) -> str:
    text = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {text}"


# --- status helpers -------------------------------------------------------------------------


def _max_status(value: float, warning: float, critical: float) -> HealthStatus:
    if value > critical:
        return HealthStatus.CRITICAL
    if value > warning:
        return HealthStatus.WARNING
    return HealthStatus.OK


def _min_status(value: float, warning: float, critical: float) -> HealthStatus:
    if value < critical:
        return HealthStatus.CRITICAL
    if value < warning:
        return HealthStatus.WARNING
    return HealthStatus.OK


def worst(statuses: Sequence[HealthStatus]) -> HealthStatus:
    """Worst evaluated state; INSUFFICIENT_DATA only when nothing could be evaluated."""
    evaluated = [s for s in statuses if s != HealthStatus.INSUFFICIENT_DATA]
    if not evaluated:
        return HealthStatus.INSUFFICIENT_DATA
    return min(evaluated, key=lambda s: _SEVERITY[s])


def _insufficient(
    key: str,
    title: str,
    explanation: str,
    *,
    observations: int | None = None,
    min_observations: int | None = None,
    unit: HealthUnit = HealthUnit.FRACTION,
) -> HealthCheck:
    return HealthCheck(
        key=key,
        title=title,
        status=HealthStatus.INSUFFICIENT_DATA,
        explanation=explanation,
        unit=unit,
        observations=observations,
        min_observations=min_observations,
    )


def _pillar(pillar: HealthPillar, checks: list[HealthCheck]) -> PillarResult:
    return PillarResult(
        pillar=pillar,
        title=PILLAR_TITLES[pillar],
        status=worst([c.status for c in checks]),
        checks=checks,
    )


# --- grouping -------------------------------------------------------------------------------

_B3_ROOT = re.compile(r"^([A-Z]{4})\d{1,2}F?$")


def issuer_of(holding: Holding) -> str:
    """Issuer used for concentration: the bond issuer or the B3 ticker root (PETR3/PETR4)."""
    if holding.issuer:
        return holding.issuer.strip().upper()
    if holding.asset_type == AssetType.TREASURY:
        return "TESOURO NACIONAL"
    match = _B3_ROOT.match(holding.ticker)
    return match.group(1) if match else holding.ticker


def _sum_by(holdings: Sequence[Holding], key: Callable[[Holding], str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for h in holdings:
        label = key(h)
        out[label] = out.get(label, 0.0) + h.value_brl
    return out


def _breakdown(dimension: str, values: Mapping[str, float]) -> ConcentrationBreakdown | None:
    conc: Concentration | None = concentration(values)
    if conc is None:
        return None
    return ConcentrationBreakdown(
        dimension=dimension,
        hhi=conc.hhi,
        effective_count=conc.effective_count,
        weights={k: round(v, 4) for k, v in conc.weights.items()},
    )


# --- pillars ----------------------------------------------------------------------------------


def _policy_pillar(
    inputs: HealthInputs, holdings: Sequence[Holding], total: float
) -> list[HealthCheck]:
    checks: list[HealthCheck] = []
    if total <= 0 or not inputs.allocations:
        checks.append(
            _insufficient(
                "band_adherence", "Quadrantes dentro da banda", "A carteira ainda não tem valor."
            )
        )
    else:
        outside = [a for a in inputs.allocations if a.band_status != BAND_WITHIN]
        deepest = max((abs(a.deviation_pct) for a in inputs.allocations), default=0.0)
        if not outside:
            checks.append(
                HealthCheck(
                    key="band_adherence",
                    title="Quadrantes dentro da banda",
                    status=HealthStatus.OK,
                    value=deepest / 100.0,
                    explanation="Todos os quadrantes ARCA estão dentro da banda de tolerância.",
                )
            )
        else:
            critical = any(abs(a.deviation_pct) > 2 * a.band_pct for a in outside)
            parts = []
            for a in sorted(outside, key=lambda x: -abs(x.deviation_pct)):
                side = "acima" if a.band_status == BAND_ABOVE else "abaixo"
                days = inputs.class_out_of_band_days.get(a.arca_class)
                since = f", há {days} dias" if days else ""
                parts.append(
                    f"{ARCA_LABELS[a.arca_class]} {_num(abs(a.deviation_pct), 1)} p.p. {side} "
                    f"(banda {_num(a.band_pct, 1)} p.p.{since})"
                )
            checks.append(
                HealthCheck(
                    key="band_adherence",
                    title="Quadrantes dentro da banda",
                    status=HealthStatus.CRITICAL if critical else HealthStatus.WARNING,
                    value=deepest / 100.0,
                    explanation=f"{plural(len(parts), 'quadrante', 'quadrantes')} fora da banda:",
                    items=parts,
                    action=(
                        "Direcione os próximos aportes para os quadrantes abaixo da banda "
                        "(o simulador de aporte já os prioriza). Um desvio maior que o dobro "
                        "da banda pede rebalanceamento."
                    ),
                )
            )

    arca = [h for h in holdings if h.purpose == AssetPurpose.ARCA]
    ineligible = [h for h in arca if not h.eligible]
    weight = sum(h.value_brl for h in ineligible) / total if total > 0 else 0.0
    checks.append(
        HealthCheck(
            key="ineligible_weight",
            title="Ativos fora da elegibilidade com peso",
            status=HealthStatus.WARNING if ineligible else HealthStatus.OK,
            value=round(weight, 4),
            explanation=(
                f"{plural(len(ineligible), 'ativo', 'ativos')} fora dos critérios de "
                f"elegibilidade {'soma' if len(ineligible) == 1 else 'somam'} "
                f"{_pct(weight)} da carteira: {', '.join(h.ticker for h in ineligible)}."
                if ineligible
                else "Todos os ativos com peso atendem aos critérios de elegibilidade."
            ),
            action=(
                "Revise o checklist desses ativos ou planeje a saída; eles não recebem aportes."
                if ineligible
                else None
            ),
        )
    )
    return checks


def _concentration_pillar(
    holdings: Sequence[Holding], total: float, policy: HealthPolicy
) -> tuple[list[HealthCheck], list[ConcentrationBreakdown], list[InstitutionExposure]]:
    checks: list[HealthCheck] = []
    breakdowns: list[ConcentrationBreakdown] = []
    if total <= 0:
        return (
            [_insufficient("largest_asset", "Maior ativo", "A carteira ainda não tem valor.")],
            breakdowns,
            [],
        )

    private = [h for h in holdings if h.asset_type not in SOVEREIGN_TYPES]
    weights = {h.ticker: h.value_brl / total for h in private}
    if weights:
        largest_ticker, largest = max(weights.items(), key=lambda kv: kv[1])
        checks.append(
            HealthCheck(
                key="largest_asset",
                title="Maior ativo",
                status=_max_status(
                    largest, policy.max_asset_weight_warning, policy.max_asset_weight_critical
                ),
                value=round(largest, 4),
                warning_threshold=policy.max_asset_weight_warning,
                critical_threshold=policy.max_asset_weight_critical,
                explanation=(
                    f"{largest_ticker} representa {_pct(largest)} da carteira "
                    "(Tesouro e caixa não entram nesta conta)."
                ),
                action=(
                    f"Pare de aportar em {largest_ticker} até o peso voltar ao limite."
                    if largest > policy.max_asset_weight_warning
                    else None
                ),
            )
        )
        top5 = top_weight(weights, 5)
        checks.append(
            HealthCheck(
                key="top5_assets",
                title="Cinco maiores ativos",
                status=_max_status(
                    top5, policy.max_top5_weight_warning, policy.max_top5_weight_critical
                ),
                value=round(top5, 4),
                warning_threshold=policy.max_top5_weight_warning,
                critical_threshold=policy.max_top5_weight_critical,
                explanation=f"Os cinco maiores ativos somam {_pct(top5)} da carteira.",
                action=(
                    "Distribua os próximos aportes entre mais ativos do quadrante."
                    if top5 > policy.max_top5_weight_warning
                    else None
                ),
            )
        )
        effective = concentration({h.ticker: h.value_brl for h in private})
        if effective is not None:
            checks.append(
                HealthCheck(
                    key="effective_assets",
                    title="Número efetivo de ativos",
                    status=_min_status(
                        effective.effective_count,
                        policy.min_effective_assets_warning,
                        policy.min_effective_assets_critical,
                    ),
                    value=effective.effective_count,
                    unit=HealthUnit.COUNT,
                    warning_threshold=policy.min_effective_assets_warning,
                    critical_threshold=policy.min_effective_assets_critical,
                    explanation=(
                        f"{len(private)} ativos equivalem a {_num(effective.effective_count, 1)} "
                        f"ativos de mesmo peso (HHI {_num(effective.hhi, 3)})."
                    ),
                    action=(
                        "Aumente o número de ativos ou reduza a diferença de pesos entre eles."
                        if effective.effective_count < policy.min_effective_assets_warning
                        else None
                    ),
                )
            )

    variable = [
        h
        for h in holdings
        if h.asset_type in VARIABLE_INCOME_TYPES and h.asset_type not in DIVERSIFIED_TYPES
    ]
    variable_total = sum(h.value_brl for h in variable)
    if variable_total > 0:
        by_sector = _sum_by(variable, lambda h: h.sector or UNKNOWN_SECTOR)
        known = {k: v / variable_total for k, v in by_sector.items() if k != UNKNOWN_SECTOR}
        if known:
            sector, sector_weight = max(known.items(), key=lambda kv: kv[1])
            unknown = by_sector.get(UNKNOWN_SECTOR, 0.0) / variable_total
            note = f" {_pct(unknown)} da renda variável não tem setor informado." if unknown else ""
            checks.append(
                HealthCheck(
                    key="largest_sector",
                    title="Maior setor da renda variável",
                    status=_max_status(
                        sector_weight,
                        policy.max_sector_weight_warning,
                        policy.max_sector_weight_critical,
                    ),
                    value=round(sector_weight, 4),
                    warning_threshold=policy.max_sector_weight_warning,
                    critical_threshold=policy.max_sector_weight_critical,
                    explanation=(
                        f"{sector} concentra {_pct(sector_weight)} da renda variável.{note}"
                    ),
                    action=(
                        f"Busque ativos de outros setores antes de aportar de novo em {sector}."
                        if sector_weight > policy.max_sector_weight_warning
                        else None
                    ),
                )
            )
        else:
            checks.append(
                _insufficient(
                    "largest_sector",
                    "Maior setor da renda variável",
                    "Os provedores não informaram o setor de nenhum ativo de renda variável.",
                )
            )
        sector_breakdown = _breakdown("SECTOR", by_sector)
        if sector_breakdown:
            breakdowns.append(sector_breakdown)

    institutions: list[InstitutionExposure] = []
    covered = [h for h in holdings if h.fgc_covered]
    if covered:
        by_issuer = _sum_by(covered, lambda h: (h.issuer or "").strip().upper())
        unknown_value = by_issuer.pop("", 0.0)
        for issuer, value in sorted(by_issuer.items(), key=lambda kv: -kv[1]):
            institutions.append(
                InstitutionExposure(
                    issuer=issuer,
                    value_brl=round(value, 2),
                    limit_brl=policy.fgc_limit_brl,
                    usage=round(value / policy.fgc_limit_brl, 4),
                )
            )
        top = institutions[0] if institutions else None
        usage = top.usage if top else 0.0
        if usage > 1.0:
            status = HealthStatus.CRITICAL
        elif usage > policy.fgc_warning_ratio or unknown_value > 0:
            status = HealthStatus.WARNING
        else:
            status = HealthStatus.OK
        above = [i for i in institutions if i.usage > 1.0]
        explanation = (
            f"Maior exposição: {top.issuer} com {_brl(top.value_brl)} ({_pct(usage, 0)} do "
            f"limite de {_brl(policy.fgc_limit_brl)} do FGC)."
            if top
            else "Os títulos cobertos pelo FGC não têm emissor informado."
        )
        if unknown_value > 0 and top:
            explanation += f" {_brl(unknown_value)} em títulos sem emissor informado."
        checks.append(
            HealthCheck(
                key="fgc_exposure",
                title="Exposição por instituição (FGC)",
                status=status,
                value=round(usage, 4),
                warning_threshold=policy.fgc_warning_ratio,
                critical_threshold=1.0,
                explanation=explanation,
                action=(
                    "O excedente de "
                    + ", ".join(f"{i.issuer} ({_brl(i.value_brl - i.limit_brl)})" for i in above)
                    + " não tem garantia: distribua entre outras instituições."
                    if above
                    else (
                        "Informe o emissor dos títulos para conferir o limite do FGC."
                        if unknown_value > 0
                        else None
                    )
                ),
            )
        )

    for dimension, values in (
        ("ASSET", _sum_by(holdings, lambda h: h.ticker)),
        ("ISSUER", _sum_by(holdings, issuer_of)),
        ("CLASS", _sum_by(holdings, lambda h: h.arca_class.value)),
    ):
        breakdown = _breakdown(dimension, values)
        if breakdown:
            breakdowns.append(breakdown)
    order = {"ASSET": 0, "SECTOR": 1, "ISSUER": 2, "CLASS": 3}
    breakdowns.sort(key=lambda b: order[b.dimension])
    return checks, breakdowns, institutions


def _diversification_pillar(
    inputs: HealthInputs, holdings: Sequence[Holding], policy: HealthPolicy
) -> tuple[list[HealthCheck], DiversificationDetail]:
    values = {h.ticker: h.value_brl for h in holdings if h.value_brl > 0}
    series = {t: list(s)[-ROLLING_WINDOW:] for t, s in inputs.asset_returns.items() if t in values}
    estimate = estimate_covariance(series, min_observations=policy.min_observations)
    titles = (
        ("diversification_ratio", "Índice de diversificação (Choueifaty)"),
        ("risk_contribution", "Contribuição ao risco"),
        ("correlated_pairs", "Pares muito correlacionados"),
    )
    if estimate is None or len(estimate.names) < 2:
        known = max((sum(v is not None for v in s) for s in series.values()), default=0)
        explanation = (
            f"São necessários ao menos dois ativos com {policy.min_observations} retornos "
            "diários de histórico de preço."
        )
        return (
            [
                _insufficient(
                    key,
                    title,
                    explanation,
                    observations=known,
                    min_observations=policy.min_observations,
                    unit=HealthUnit.RATIO
                    if key == "diversification_ratio"
                    else HealthUnit.FRACTION,
                )
                for key, title in titles
            ],
            DiversificationDetail(excluded=sorted(values)),
        )

    decomposition = decompose_risk(estimate, values)
    by_class: dict[ArcaClass, tuple[float, float]] = {}
    class_of = {h.ticker: h.arca_class for h in holdings}
    for name in estimate.names:
        w, r = by_class.get(class_of[name], (0.0, 0.0))
        by_class[class_of[name]] = (
            w + decomposition.weights.get(name, 0.0),
            r + decomposition.risk_shares.get(name, 0.0),
        )
    risky = [n for i, n in enumerate(estimate.names) if estimate.volatilities[i] > 0]
    correlations = sample_correlations(series, risky)
    high = sorted(
        (
            CorrelatedPair(a, b, c)
            for (a, b), c in correlations.items()
            if c >= policy.high_correlation
        ),
        key=lambda p: -p.correlation,
    )
    detail = DiversificationDetail(
        observations=estimate.observations,
        shrinkage=estimate.shrinkage,
        volatility=decomposition.volatility,
        diversification_ratio=decomposition.diversification_ratio,
        by_asset=sorted(
            (
                RiskShare(
                    n, decomposition.weights.get(n, 0.0), decomposition.risk_shares.get(n, 0.0)
                )
                for n in estimate.names
            ),
            key=lambda s: -s.risk_share,
        ),
        by_class=sorted(
            (RiskShare(c.value, round(w, 4), round(r, 4)) for c, (w, r) in by_class.items()),
            key=lambda s: -s.risk_share,
        ),
        correlated_pairs=high,
        excluded=sorted(set(values) - set(estimate.names)),
    )

    checks: list[HealthCheck] = []
    ratio = decomposition.diversification_ratio
    if ratio is None:
        checks.append(
            _insufficient(
                titles[0][0], titles[0][1], "Os ativos com histórico não oscilaram no período."
            )
        )
    else:
        checks.append(
            HealthCheck(
                key="diversification_ratio",
                title=titles[0][1],
                status=_min_status(
                    ratio,
                    policy.min_diversification_ratio_warning,
                    policy.min_diversification_ratio_critical,
                ),
                value=ratio,
                unit=HealthUnit.RATIO,
                warning_threshold=policy.min_diversification_ratio_warning,
                critical_threshold=policy.min_diversification_ratio_critical,
                observations=estimate.observations,
                min_observations=policy.min_observations,
                explanation=(
                    f"A volatilidade média ponderada dos ativos é {_num(ratio)} vezes a "
                    f"volatilidade da carteira ({_pct(decomposition.volatility)} a.a.). "
                    "Quanto maior, mais as oscilações se compensam (1 = sem diversificação)."
                ),
                action=(
                    "Inclua ativos de comportamento diferente (outros quadrantes, setores ou "
                    "moedas) em vez de mais ativos parecidos."
                    if ratio < policy.min_diversification_ratio_warning
                    else None
                ),
            )
        )

    top = detail.by_asset[0] if detail.by_asset else None
    if top is None or decomposition.volatility <= 0:
        checks.append(
            _insufficient(titles[1][0], titles[1][1], "A carteira não oscilou no período.")
        )
    else:
        heavy = top.risk_share > policy.max_asset_risk_share
        class_items = [
            f"{ARCA_LABELS[ArcaClass(s.label)]}: {_pct(s.weight, 0)} do peso e "
            f"{_pct(s.risk_share, 0)} do risco"
            for s in detail.by_class
        ]
        checks.append(
            HealthCheck(
                key="risk_contribution",
                title=titles[1][1],
                status=HealthStatus.WARNING if heavy else HealthStatus.OK,
                value=top.risk_share,
                warning_threshold=policy.max_asset_risk_share,
                observations=estimate.observations,
                explanation=(
                    f"{top.label} responde por {_pct(top.risk_share)} do risco com "
                    f"{_pct(top.weight)} do peso. Por quadrante:"
                ),
                items=class_items,
                action=(
                    f"Reduza o peso de {top.label} ou aporte em ativos que oscilem menos."
                    if heavy
                    else None
                ),
            )
        )

    checks.append(
        HealthCheck(
            key="correlated_pairs",
            title=titles[2][1],
            status=HealthStatus.WARNING if high else HealthStatus.OK,
            value=float(len(high)),
            unit=HealthUnit.COUNT,
            warning_threshold=policy.high_correlation,
            observations=estimate.observations,
            explanation=(
                f"{len(high)} par(es) com correlação acima de {_num(policy.high_correlation)}:"
                if high
                else f"Nenhum par com correlação acima de {_num(policy.high_correlation)}."
            ),
            items=[f"{p.first} × {p.second} ({_num(p.correlation)})" for p in high[:5]],
            action=(
                "Ativos muito correlacionados se comportam como um só: avalie manter apenas o "
                "de melhor nota no checklist."
                if high
                else None
            ),
        )
    )
    return checks, detail


def _risk_pillar(
    inputs: HealthInputs, holdings: Sequence[Holding], policy: HealthPolicy
) -> tuple[list[HealthCheck], RiskDetail]:
    returns = list(inputs.portfolio_returns)
    n = len(returns)
    checks: list[HealthCheck] = []

    vol = annualized_volatility(returns) if n >= policy.min_observations else None
    if vol is None:
        checks.append(
            _insufficient(
                "volatility",
                "Volatilidade anualizada",
                f"São necessários {policy.min_observations} retornos diários da carteira (há {n}).",
                observations=n,
                min_observations=policy.min_observations,
            )
        )
    else:
        checks.append(
            HealthCheck(
                key="volatility",
                title="Volatilidade anualizada",
                status=_max_status(
                    vol, policy.max_volatility_warning, policy.max_volatility_critical
                ),
                value=round(vol, 4),
                warning_threshold=policy.max_volatility_warning,
                critical_threshold=policy.max_volatility_critical,
                observations=n,
                min_observations=policy.min_observations,
                explanation=f"A carteira oscila {_pct(vol)} ao ano.",
                action=(
                    "A oscilação está acima do perfil da política: aumente o peso do quadrante "
                    "Caixa ou revise os limites na Estratégia."
                    if vol > policy.max_volatility_warning
                    else None
                ),
            )
        )

    state = drawdown_state(inputs.portfolio_dates, returns)
    if n < MIN_DRAWDOWN_OBSERVATIONS:
        checks.append(
            _insufficient(
                "current_drawdown",
                "Queda desde o pico",
                f"São necessários {MIN_DRAWDOWN_OBSERVATIONS} retornos diários (há {n}).",
                observations=n,
                min_observations=MIN_DRAWDOWN_OBSERVATIONS,
            )
        )
    else:
        depth = -state.current
        checks.append(
            HealthCheck(
                key="current_drawdown",
                title="Queda desde o pico",
                status=_max_status(
                    depth, policy.max_drawdown_warning, policy.max_drawdown_critical
                ),
                value=round(depth, 4),
                warning_threshold=policy.max_drawdown_warning,
                critical_threshold=policy.max_drawdown_critical,
                observations=n,
                min_observations=MIN_DRAWDOWN_OBSERVATIONS,
                explanation=(
                    "A carteira está no pico."
                    if depth <= 0
                    else (
                        f"A carteira está {_pct(depth)} abaixo do pico"
                        + (f" de {state.peak_date.strftime('%d/%m/%Y')}" if state.peak_date else "")
                        + f", há {state.periods} pregões."
                    )
                ),
                action=(
                    "Confira se a queda vem de poucos ativos (veja a contribuição ao risco) "
                    "antes de mudar a estratégia."
                    if depth > policy.max_drawdown_warning
                    else None
                ),
            )
        )

    values = {h.ticker: h.value_brl for h in holdings if h.ticker in inputs.asset_returns}
    total = sum(values.values())
    stress: StressResult | None = None
    if total > 0:
        weights = {t: v / total for t, v in values.items()}
        replay = weighted_returns(weights, inputs.asset_returns)
        stress = historical_stress(list(inputs.asset_dates), replay, window=STRESS_WINDOW)
    if stress is None:
        checks.append(
            _insufficient(
                "historical_stress",
                "Estresse histórico com os pesos atuais",
                "Falta histórico de preço dos ativos para simular os pesos atuais.",
                min_observations=STRESS_WINDOW,
            )
        )
    else:
        loss = max(0.0, -stress.worst_window_return)
        window = (
            f" entre {stress.window_start.strftime('%d/%m/%Y')} e "
            f"{stress.window_end.strftime('%d/%m/%Y')}"
            if stress.window_start and stress.window_end
            else ""
        )
        checks.append(
            HealthCheck(
                key="historical_stress",
                title="Estresse histórico com os pesos atuais",
                status=_max_status(
                    loss, policy.max_stress_loss_warning, policy.max_stress_loss_critical
                ),
                value=round(loss, 4),
                warning_threshold=policy.max_stress_loss_warning,
                critical_threshold=policy.max_stress_loss_critical,
                observations=stress.observations,
                min_observations=STRESS_WINDOW,
                explanation=(
                    f"Com os pesos de hoje, o pior mês do histórico{window} teria custado "
                    f"{_pct(loss)}; a maior queda acumulada seria {_pct(-stress.max_drawdown)}."
                ),
                action=(
                    "Avalie se aguentaria essa perda sem vender; se não, aumente o Caixa."
                    if loss > policy.max_stress_loss_warning
                    else None
                ),
            )
        )

    detail = RiskDetail(
        observations=n,
        volatility=round(vol, 4) if vol is not None else None,
        current_drawdown=round(state.current, 4) if n else None,
        drawdown_periods=state.periods if n else None,
        peak_date=state.peak_date,
        ulcer_index=round(ulcer_index(returns), 4) if n else None,
        var_95=round(historical_var(returns), 4) if n >= policy.min_observations else None,
        cvar_95=round(conditional_var(returns), 4) if n >= policy.min_observations else None,
        stress=stress,
    )
    return checks, detail


def _performance_pillar(
    inputs: HealthInputs, policy: HealthPolicy
) -> tuple[list[HealthCheck], PerformanceDetail]:
    returns = list(inputs.portfolio_returns)
    dates = list(inputs.portfolio_dates)
    n = len(returns)
    rf = inputs.annual_cdi_rate
    enough = n >= policy.min_observations
    checks: list[HealthCheck] = []

    bench = list(inputs.benchmark_returns)
    paired_bench = [b for b in bench if b is not None]
    te = tracking_error(returns, bench) if enough else None
    ir = information_ratio(returns, bench) if enough else None
    benchmark_return = cumulative_return(paired_bench) if paired_bench else None
    if ir is None:
        checks.append(
            _insufficient(
                "information_ratio",
                "Retorno × benchmark da política",
                f"São necessários {policy.min_observations} retornos diários da carteira e do "
                f"benchmark (há {n}).",
                observations=n,
                min_observations=policy.min_observations,
                unit=HealthUnit.RATIO,
            )
        )
    else:
        cum = cumulative_return(returns)
        checks.append(
            HealthCheck(
                key="information_ratio",
                title="Retorno × benchmark da política",
                status=HealthStatus.WARNING if ir < 0 else HealthStatus.OK,
                value=round(ir, 4),
                unit=HealthUnit.RATIO,
                warning_threshold=0.0,
                observations=n,
                min_observations=policy.min_observations,
                explanation=(
                    f"TWR de {_pct(cum)} contra {_pct(benchmark_return or 0.0)} do benchmark "
                    "da política (IBOV, IFIX, S&P 500 e CDI nos pesos-alvo ARCA). "
                    f"Tracking error {_pct(te or 0.0)} a.a., Information Ratio {_num(ir)}."
                ),
                action=(
                    "A carteira rende menos que a própria alocação-alvo em índices: compare "
                    "os ativos de cada quadrante com o índice do quadrante."
                    if ir < 0
                    else None
                ),
            )
        )

    consistency, months = consistency_against(dates, returns, list(inputs.cdi_returns))
    if consistency is None or months < MIN_CONSISTENCY_MONTHS:
        checks.append(
            _insufficient(
                "cdi_consistency",
                "Consistência contra o CDI",
                f"São necessários {MIN_CONSISTENCY_MONTHS} meses com CDI e carteira (há {months}).",
                observations=months,
                min_observations=MIN_CONSISTENCY_MONTHS,
            )
        )
    else:
        low = consistency < policy.min_cdi_consistency
        checks.append(
            HealthCheck(
                key="cdi_consistency",
                title="Consistência contra o CDI",
                status=HealthStatus.WARNING if low else HealthStatus.OK,
                value=round(consistency, 4),
                warning_threshold=policy.min_cdi_consistency,
                observations=months,
                min_observations=MIN_CONSISTENCY_MONTHS,
                explanation=(
                    f"A carteira superou o CDI em {_pct(consistency, 0)} de {months} meses."
                ),
                action=(
                    "Na maior parte dos meses o CDI rendeu mais: confirme se o risco assumido "
                    "está sendo pago no longo prazo."
                    if low
                    else None
                ),
            )
        )

    rolling = rolling_windows(dates, returns, annual_risk_free_rate=rf)
    if not rolling:
        checks.append(
            _insufficient(
                "rolling_sharpe",
                "Sharpe em 12 meses móveis",
                f"São necessários {ROLLING_WINDOW} retornos diários (há {n}).",
                observations=n,
                min_observations=ROLLING_WINDOW,
                unit=HealthUnit.RATIO,
            )
        )
    else:
        last = rolling[-1]
        checks.append(
            HealthCheck(
                key="rolling_sharpe",
                title="Sharpe em 12 meses móveis",
                status=HealthStatus.WARNING if last.sharpe < 0 else HealthStatus.OK,
                value=last.sharpe,
                unit=HealthUnit.RATIO,
                warning_threshold=0.0,
                observations=n,
                min_observations=ROLLING_WINDOW,
                explanation=(
                    f"Nos últimos 12 meses: retorno de {_pct(last.cumulative_return)} e Sharpe "
                    f"de {_num(last.sharpe)}."
                ),
                action=(
                    "O último ano rendeu abaixo do CDI considerando o risco: veja se é um "
                    "quadrante específico."
                    if last.sharpe < 0
                    else None
                ),
            )
        )

    sharpe = sharpe_ratio(returns, rf) if enough else None
    intervals = bootstrap_intervals(returns, annual_risk_free_rate=rf) if enough else None
    sharpe_ci: ConfidenceInterval | None = None
    cagr_ci: ConfidenceInterval | None = None
    if sharpe is None or intervals is None:
        checks.append(
            _insufficient(
                "sharpe_confidence",
                "Sharpe com intervalo de confiança",
                f"São necessários {policy.min_observations} retornos diários (há {n}).",
                observations=n,
                min_observations=policy.min_observations,
                unit=HealthUnit.RATIO,
            )
        )
    else:
        sharpe_ci, cagr_ci = intervals
        negative = sharpe_ci.high < 0
        checks.append(
            HealthCheck(
                key="sharpe_confidence",
                title="Sharpe com intervalo de confiança",
                status=HealthStatus.WARNING if negative else HealthStatus.OK,
                value=round(sharpe, 4),
                unit=HealthUnit.RATIO,
                observations=n,
                min_observations=policy.min_observations,
                explanation=(
                    f"Sharpe de {_num(sharpe)} (IC 95%: {_num(sharpe_ci.low)} a "
                    f"{_num(sharpe_ci.high)}); retorno anualizado entre {_pct(cagr_ci.low)} e "
                    f"{_pct(cagr_ci.high)}."
                    + (
                        " O intervalo inclui zero: ainda não dá para afirmar que o risco "
                        "foi remunerado."
                        if sharpe_ci.low <= 0 <= sharpe_ci.high
                        else ""
                    )
                ),
                action=(
                    "Mesmo no melhor cenário do intervalo a carteira rende abaixo do CDI."
                    if negative
                    else None
                ),
            )
        )

    cum = cumulative_return(returns) if n else None
    detail = PerformanceDetail(
        observations=n,
        cumulative_return=round(cum, 4) if cum is not None else None,
        cagr=round(cagr(cum, n), 4) if cum is not None and enough else None,
        benchmark_return=round(benchmark_return, 4) if benchmark_return is not None else None,
        tracking_error=round(te, 4) if te is not None else None,
        information_ratio=round(ir, 4) if ir is not None else None,
        omega=(
            round(o, 4)
            if enough and (o := omega_ratio(returns, list(inputs.cdi_returns))) is not None
            else None
        ),
        sharpe=round(sharpe, 4) if sharpe is not None else None,
        sharpe_interval=sharpe_ci,
        cagr_interval=cagr_ci,
        cdi_consistency=round(consistency, 4) if consistency is not None else None,
        months_compared=months,
        rolling=rolling,
        class_returns=dict(inputs.class_returns),
    )
    return checks, detail


def _quality_pillar(
    holdings: Sequence[Holding], total: float, policy: HealthPolicy
) -> tuple[list[HealthCheck], list[HoldingQuality]]:
    checks: list[HealthCheck] = []
    rows = [
        HoldingQuality(
            ticker=h.ticker,
            weight=round(h.value_brl / total, 4) if total > 0 else 0.0,
            checklist_ratio=h.checklist_ratio,
            stale=h.checklist_stale,
            f_score=h.f_score,
            z_score=h.z_score,
        )
        for h in holdings
        if h.checklist_ratio is not None or h.f_score is not None or h.z_score is not None
    ]
    rows.sort(key=lambda r: -r.weight)

    scored = [h for h in holdings if h.checklist_ratio is not None and h.value_brl > 0]
    scored_value = sum(h.value_brl for h in scored)
    if scored_value <= 0:
        checks.append(
            _insufficient(
                "checklist_quality",
                "Nota média ponderada do checklist",
                "Nenhum ativo com peso tem checklist respondido.",
                unit=HealthUnit.RATIO,
            )
        )
    else:
        quality = sum((h.checklist_ratio or 0.0) * h.value_brl for h in scored) / scored_value
        coverage = scored_value / total if total > 0 else 0.0
        checks.append(
            HealthCheck(
                key="checklist_quality",
                title="Nota média ponderada do checklist",
                status=_min_status(
                    quality,
                    policy.min_checklist_quality_warning,
                    policy.min_checklist_quality_critical,
                ),
                value=round(quality, 4),
                unit=HealthUnit.RATIO,
                warning_threshold=policy.min_checklist_quality_warning,
                critical_threshold=policy.min_checklist_quality_critical,
                explanation=(
                    f"Nota média de {_num(quality)} (de -1 a 1: saldo de sim e não sobre as "
                    f"perguntas aplicáveis), cobrindo {_pct(coverage)} da carteira."
                ),
                action=(
                    "Os ativos de maior peso têm teses fracas: revise o checklist deles antes "
                    "do próximo aporte."
                    if quality < policy.min_checklist_quality_warning
                    else None
                ),
            )
        )

    answered = [h for h in scored if h.checklist_age_days is not None]
    if not answered:
        checks.append(
            HealthCheck(
                key="stale_checklist",
                title="Peso com checklist vencido",
                status=HealthStatus.OK,
                value=0.0,
                warning_threshold=policy.max_stale_checklist_weight,
                explanation="Nenhum ativo com peso tem respostas manuais no checklist.",
            )
        )
    else:
        stale = [h for h in answered if h.checklist_stale]
        weight = sum(h.value_brl for h in stale) / total if total > 0 else 0.0
        too_much = weight > policy.max_stale_checklist_weight
        checks.append(
            HealthCheck(
                key="stale_checklist",
                title="Peso com checklist vencido",
                status=HealthStatus.WARNING if too_much else HealthStatus.OK,
                value=round(weight, 4),
                warning_threshold=policy.max_stale_checklist_weight,
                explanation=(
                    f"{plural(len(stale), 'ativo', 'ativos')}"
                    f" com respostas manuais vencidas (prazo de validade da "
                    f"elegibilidade ou demonstrativo anual mais novo) somam {_pct(weight)} da "
                    "carteira" + (f": {', '.join(h.ticker for h in stale)}." if stale else ".")
                ),
                action=(
                    "Revise as respostas manuais desses ativos com o último demonstrativo."
                    if stale
                    else None
                ),
            )
        )

    suspicious = [h for h in holdings if h.suspicious_data]
    suspicious_weight = sum(h.value_brl for h in suspicious) / total if total > 0 else 0.0
    checks.append(
        HealthCheck(
            key="suspicious_data",
            title="Peso com dado suspeito",
            status=HealthStatus.WARNING if suspicious else HealthStatus.OK,
            value=round(suspicious_weight, 4),
            explanation=(
                f"{plural(len(suspicious), 'ativo', 'ativos')}"
                f" com indicadores fora da faixa plausível ou "
                f"divergentes entre fontes somam {_pct(suspicious_weight)} da carteira: "
                f"{', '.join(h.ticker for h in suspicious)}."
                if suspicious
                else "Nenhum ativo com peso tem indicador marcado como suspeito."
            ),
            action=(
                "Confira os indicadores desses ativos antes de usar o valuation e o checklist."
                if suspicious
                else None
            ),
        )
    )

    with_scores = [h for h in holdings if h.f_score is not None or h.z_score is not None]
    if not with_scores:
        checks.append(
            _insufficient(
                "accounting_scores",
                "Piotroski F-score e Altman Z''-score",
                "Os demonstrativos armazenados não trazem as linhas necessárias (ativo total, "
                "fluxo de caixa operacional, ativo e passivo circulantes, lucros retidos, EBIT).",
                unit=HealthUnit.COUNT,
            )
        )
    else:
        weak = [
            h
            for h in with_scores
            if (h.f_score is not None and h.f_score <= LOW_F_SCORE)
            or (h.z_score is not None and h.z_score < Z_DISTRESS)
        ]
        weight = sum(h.value_brl for h in weak) / total if total > 0 else 0.0
        checks.append(
            HealthCheck(
                key="accounting_scores",
                title="Piotroski F-score e Altman Z''-score",
                status=HealthStatus.WARNING if weak else HealthStatus.OK,
                value=round(weight, 4),
                explanation=(
                    f"{plural(len(weak), 'ativo', 'ativos')}"
                    f" com F-score até {LOW_F_SCORE} ou Z''-score abaixo de "
                    f"{_num(Z_DISTRESS, 1)} somam {_pct(weight)} da carteira: "
                    f"{', '.join(h.ticker for h in weak)}."
                    if weak
                    else f"{plural(len(with_scores), 'ativo avaliado', 'ativos avaliados')}"
                    f" sem sinal de fragilidade contábil."
                ),
                action=(
                    "Confira o endividamento e a geração de caixa dessas empresas."
                    if weak
                    else None
                ),
            )
        )
    return checks, rows


def _liquidity_pillar(
    inputs: HealthInputs, holdings: Sequence[Holding], total: float, policy: HealthPolicy
) -> tuple[list[HealthCheck], LiquidityDetail]:
    checks: list[HealthCheck] = []
    reserve = sum(h.value_brl for h in holdings if h.purpose == AssetPurpose.EMERGENCY_RESERVE)
    months: float | None = None
    if policy.monthly_expenses_brl is None:
        checks.append(
            _insufficient(
                "emergency_reserve",
                "Reserva de emergência",
                f"Reserva atual de {_brl(reserve)}. Informe o custo de vida mensal na "
                "Estratégia para medir quantos meses ela cobre.",
                unit=HealthUnit.MONTHS,
            )
        )
    else:
        months = reserve / policy.monthly_expenses_brl
        checks.append(
            HealthCheck(
                key="emergency_reserve",
                title="Reserva de emergência",
                status=_min_status(
                    months, policy.min_reserve_months_warning, policy.min_reserve_months_critical
                ),
                value=round(months, 2),
                unit=HealthUnit.MONTHS,
                warning_threshold=policy.min_reserve_months_warning,
                critical_threshold=policy.min_reserve_months_critical,
                explanation=(
                    f"A reserva de {_brl(reserve)} cobre {_num(months, 1)} meses de um custo "
                    f"mensal de {_brl(policy.monthly_expenses_brl)}."
                ),
                action=(
                    "Complete a reserva antes de aportar nos quadrantes de risco."
                    if months < policy.min_reserve_months_warning
                    else None
                ),
            )
        )

    liquid_weight = sum(h.value_brl for h in holdings if h.liquid_d2) / total if total > 0 else None
    if liquid_weight is None:
        checks.append(
            _insufficient("liquid_weight", "Liquidez em até D+2", "A carteira ainda não tem valor.")
        )
    else:
        low = liquid_weight < policy.min_liquid_weight
        checks.append(
            HealthCheck(
                key="liquid_weight",
                title="Liquidez em até D+2",
                status=HealthStatus.WARNING if low else HealthStatus.OK,
                value=round(liquid_weight, 4),
                warning_threshold=policy.min_liquid_weight,
                explanation=f"{_pct(liquid_weight)} da carteira pode virar dinheiro em até D+2.",
                action=(
                    "Prefira títulos com liquidez diária nos próximos aportes do Caixa."
                    if low
                    else None
                ),
            )
        )

    horizon = inputs.as_of + timedelta(days=365)
    maturities = sorted(
        (
            Maturity(h.ticker, h.maturity_date, round(h.value_brl, 2))
            for h in holdings
            if h.maturity_date is not None and inputs.as_of <= h.maturity_date <= horizon
        ),
        key=lambda m: m.maturity_date,
    )
    maturing = sum(m.value_brl for m in maturities)
    checks.append(
        HealthCheck(
            key="maturities_12m",
            title="Vencimentos em 12 meses",
            status=HealthStatus.OK,
            value=round(maturing, 2),
            unit=HealthUnit.BRL,
            explanation=(
                f"{plural(len(maturities), 'título vence', 'títulos vencem')}"
                f" em 12 meses, somando {_brl(maturing)}"
                + (
                    f"; o primeiro é {maturities[0].ticker} em "
                    f"{maturities[0].maturity_date.strftime('%d/%m/%Y')}."
                    if maturities
                    else "."
                )
            ),
            action=(
                "Planeje onde reinvestir esses valores para não deixá-los parados."
                if maturities
                else None
            ),
        )
    )

    income = inputs.earnings_12m_brl
    checks.append(
        HealthCheck(
            key="passive_income",
            title="Renda passiva em 12 meses",
            status=HealthStatus.OK,
            value=round(income, 2),
            unit=HealthUnit.BRL,
            explanation=(
                f"{_brl(income)} recebidos em proventos nos últimos 12 meses "
                f"({_brl(income / 12)} por mês"
                + (f", {_pct(income / total)} da carteira)." if total > 0 else ").")
            ),
        )
    )

    fixed = [h for h in holdings if h.asset_type in (AssetType.FIXED_INCOME, AssetType.TREASURY)]
    fixed_total = sum(h.value_brl for h in fixed)
    exempt_weight = (
        sum(h.value_brl for h in fixed if h.tax_exempt) / fixed_total if fixed_total > 0 else None
    )
    checks.append(
        HealthCheck(
            key="exempt_weight",
            title="Renda fixa isenta de IR",
            status=HealthStatus.OK,
            value=round(exempt_weight, 4) if exempt_weight is not None else None,
            explanation=(
                f"{_pct(exempt_weight)} da renda fixa é isenta de IR (LCI, LCA, CRI, CRA e "
                "debêntures incentivadas)."
                if exempt_weight is not None
                else "A carteira não tem renda fixa."
            ),
        )
    )

    window = [
        lot for lot in inputs.bracket_lots if lot.days_to_next_bracket <= policy.bracket_window_days
    ]
    window.sort(key=lambda lot: lot.days_to_next_bracket)
    saving = sum(lot.tax_saving_by_waiting for lot in window)
    checks.append(
        HealthCheck(
            key="tax_brackets",
            title="Lotes perto de mudar de faixa de IR",
            status=HealthStatus.WARNING if window else HealthStatus.OK,
            value=float(len(window)),
            unit=HealthUnit.COUNT,
            warning_threshold=float(policy.bracket_window_days),
            explanation=(
                f"{plural(len(window), 'lote muda', 'lotes mudam')}"
                f" de faixa em até {policy.bracket_window_days} dias; "
                f"esperar economiza {_brl(saving)} de IR. O próximo é {window[0].ticker} em "
                f"{window[0].next_bracket_date.strftime('%d/%m/%Y')} "
                f"({_pct(window[0].current_rate)} → {_pct(window[0].next_rate)})."
                if window
                else f"Nenhum lote muda de faixa nos próximos {policy.bracket_window_days} dias."
            ),
            action=(
                "Se precisar resgatar, prefira outros títulos ou espere a data da nova faixa."
                if window
                else None
            ),
        )
    )
    detail = LiquidityDetail(
        reserve_brl=round(reserve, 2),
        reserve_months=round(months, 2) if months is not None else None,
        liquid_weight=round(liquid_weight, 4) if liquid_weight is not None else None,
        maturities_12m=maturities,
        passive_income_12m_brl=round(income, 2),
        exempt_weight=round(exempt_weight, 4) if exempt_weight is not None else None,
        bracket_lots=window,
    )
    return checks, detail


# Checks computed from each series: they carry the note of what was dropped from it.
ASSET_SERIES_CHECKS = frozenset(
    {"diversification_ratio", "risk_contribution", "correlated_pairs", "historical_stress"}
)
PORTFOLIO_SERIES_CHECKS = frozenset(
    {
        "volatility",
        "current_drawdown",
        "information_ratio",
        "cdi_consistency",
        "rolling_sharpe",
        "sharpe_confidence",
    }
)


def _mark_suspicious(checks: list[HealthCheck], inputs: HealthInputs) -> list[HealthCheck]:
    asset_note = (
        "Dados descartados antes do cálculo: " + "; ".join(inputs.asset_data_notes) + "."
        if inputs.asset_data_notes
        else None
    )
    portfolio_note = (
        "Dias com retorno impossível da carteira (aporte ou dado errado) ficaram de fora: "
        + ", ".join(inputs.portfolio_data_notes)
        + "."
        if inputs.portfolio_data_notes
        else None
    )
    out = []
    for check in checks:
        note = (
            asset_note
            if check.key in ASSET_SERIES_CHECKS
            else portfolio_note
            if check.key in PORTFOLIO_SERIES_CHECKS
            else None
        )
        out.append(replace(check, suspicious=note) if note else check)
    return out


def diagnose(inputs: HealthInputs, policy: HealthPolicy) -> HealthReport:
    """Run every pillar and order them worst first."""
    holdings = [h for h in inputs.holdings if h.value_brl > 0 and math.isfinite(h.value_brl)]
    total = sum(h.value_brl for h in holdings)

    policy_checks = _policy_pillar(inputs, holdings, total)
    concentration_checks, breakdowns, institutions = _concentration_pillar(holdings, total, policy)
    diversification_checks, diversification = _diversification_pillar(inputs, holdings, policy)
    risk_checks, risk = _risk_pillar(inputs, holdings, policy)
    performance_checks, performance = _performance_pillar(inputs, policy)
    quality_checks, quality = _quality_pillar(holdings, total, policy)
    liquidity_checks, liquidity = _liquidity_pillar(inputs, holdings, total, policy)

    diversification_checks = _mark_suspicious(diversification_checks, inputs)
    risk_checks = _mark_suspicious(risk_checks, inputs)
    performance_checks = _mark_suspicious(performance_checks, inputs)

    pillars = [
        _pillar(HealthPillar.POLICY, policy_checks),
        _pillar(HealthPillar.CONCENTRATION, concentration_checks),
        _pillar(HealthPillar.DIVERSIFICATION, diversification_checks),
        _pillar(HealthPillar.RISK, risk_checks),
        _pillar(HealthPillar.PERFORMANCE, performance_checks),
        _pillar(HealthPillar.QUALITY, quality_checks),
        _pillar(HealthPillar.LIQUIDITY, liquidity_checks),
    ]
    pillars.sort(key=lambda p: (_SEVERITY[p.status], _PILLAR_ORDER[p.pillar]))
    return HealthReport(
        as_of_date=inputs.as_of,
        status=worst([p.status for p in pillars]),
        total_value_brl=round(total, 2),
        pillars=pillars,
        concentration=breakdowns,
        institutions=institutions,
        diversification=diversification,
        risk=risk,
        performance=performance,
        quality=quality,
        liquidity=liquidity,
    )


__all__ = [
    "BracketLot",
    "HealthCheck",
    "HealthInputs",
    "HealthPillar",
    "HealthReport",
    "HealthStatus",
    "HealthUnit",
    "Holding",
    "PillarResult",
    "diagnose",
    "issuer_of",
    "worst",
]
