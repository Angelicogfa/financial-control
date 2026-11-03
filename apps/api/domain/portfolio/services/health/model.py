"""Statuses, pillars, thresholds and the inputs/outputs of the health diagnosis."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from domain.policy.services.allocation import ClassAllocation
from domain.portfolio.services.risk_metrics import (
    ConfidenceInterval,
    RollingPoint,
    StressResult,
)
from domain.shared.enums import ArcaClass, AssetPurpose, AssetType

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
