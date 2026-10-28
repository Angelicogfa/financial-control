"""Pydantic request/response DTOs for the portfolio module.

Scope: consolidated portfolio, ARCA allocation, snapshots and analytics.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from controllers.shared.responses import CerradoEvaluationDTO
from domain.market.entities import QuoteFreshness
from domain.portfolio.services.health import HealthPillar, HealthStatus, HealthUnit
from domain.shared.enums import (
    ArcaClass,
    AssetLifecycle,
    AssetPurpose,
    AssetType,
    IntraClassStrategy,
)


class FixedIncomeValuationDTO(BaseModel):
    invested_principal: float
    gross_value: float
    gross_yield: float
    gross_yield_pct: float
    iof_tax: float
    income_tax_rate: float
    income_tax: float
    net_value: float
    net_yield: float
    net_yield_pct: float
    projected_12m_net_yield: float
    realized_pnl: float = 0.0
    curve_coverage: float = 1.0


class ValuedPositionDTO(BaseModel):
    asset_id: int
    ticker: str
    name: str
    asset_type: AssetType
    arca_class: ArcaClass
    currency: str
    quantity: float
    average_price: float
    current_unit_price: float
    fx_rate: float
    price_freshness: QuoteFreshness
    invested_value_brl: float
    gross_current_value_brl: float
    estimated_tax_brl: float
    current_value_brl: float
    unrealized_pnl_brl: float
    unrealized_pnl_pct: float
    realized_pnl_brl: float
    received_earnings_brl: float
    earnings_12m_brl: float
    yield_on_cost_pct: float
    estimated_yield_to_date_brl: float
    estimated_yield_to_date_pct: float
    estimated_yield_basis: str
    projected_12m_yield_brl: float
    consolidated_pnl_brl: float
    consolidated_return_pct: float
    cerrado_evaluation: CerradoEvaluationDTO
    class_target_weight_pct: float
    class_current_weight_pct: float
    fixed_income_details: FixedIncomeValuationDTO | None = None
    fx_pnl_brl: float = 0.0
    custom_class_weight: float | None = None
    ledger_status: str = "VALID"
    ledger_message: str | None = None
    purpose: AssetPurpose = AssetPurpose.ARCA
    lifecycle_status: AssetLifecycle = AssetLifecycle.HELD
    eligible: bool = True


class ClassAllocationDTO(BaseModel):
    arca_class: ArcaClass
    label: str
    invested_value: float
    current_value: float
    current_pct: float
    target_pct: float
    deviation_pct: float
    gap_value: float
    consolidated_pnl: float
    band_pct: float = 0.0
    band_status: str = "WITHIN"


class PortfolioReportResponseDTO(BaseModel):
    as_of_date: date
    total_invested_brl: float
    total_gross_value_brl: float
    total_estimated_tax_brl: float
    total_current_value_brl: float
    total_unrealized_pnl_brl: float
    total_unrealized_pnl_pct: float
    total_realized_pnl_brl: float
    total_received_earnings_brl: float
    total_earnings_12m_brl: float
    portfolio_yield_on_cost_pct: float
    total_estimated_yield_to_date_brl: float
    total_projected_12m_yield_brl: float
    total_projected_12m_value_brl: float
    total_consolidated_pnl_brl: float
    total_consolidated_return_pct: float
    allocations: list[ClassAllocationDTO]
    positions: list[ValuedPositionDTO]
    earnings_by_month: dict[str, float]
    total_fx_pnl_brl: float = 0.0
    projection_assumptions: dict[str, float | None] = Field(default_factory=dict)
    value_by_purpose_brl: dict[str, float] = Field(default_factory=dict)


class ContributionSimulationRequest(BaseModel):
    """Payload to simulate a 2-level contribution across ARCA classes and assets."""

    amount_brl: float = Field(..., ge=0.0)
    strategy_override: IntraClassStrategy | None = None


class AssetContributionOrderDTO(BaseModel):
    asset_id: int
    ticker: str
    name: str
    asset_type: AssetType
    arca_class: ArcaClass
    cerrado_score: int
    cerrado_recommendation: str
    intra_class_target_weight_pct: float
    allocated_amount_brl: float
    unit_price_brl: float
    recommended_quantity: float
    executed_amount_brl: float
    projected_value_brl: float


class ContributionPlanResponseDTO(BaseModel):
    contribution_amount_brl: float
    executed_total_brl: float
    unallocated_cash_brl: float
    by_class_allocated_brl: dict[ArcaClass, float]
    orders: list[AssetContributionOrderDTO]
    projected_allocations: list[ClassAllocationDTO]


class BenchmarkComparisonDTO(BaseModel):
    benchmark: str
    benchmark_return: float
    excess_return: float
    beta: float | None = None
    alpha_annual: float | None = None
    correlation: float | None = None


class SnapshotPointDTO(BaseModel):
    """One daily portfolio snapshot (home sparklines and patrimony evolution)."""

    snapshot_date: date
    invested_value: float
    market_value: float
    consolidated_pnl: float
    earnings_cum: float
    net_flow: float


class RiskReturnSummaryDTO(BaseModel):
    observations: int
    cumulative_return: float
    cagr: float
    real_return_vs_ipca: float
    annualized_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    var_95_historical: float
    var_95_parametric: float
    cvar_95: float
    benchmarks: list[BenchmarkComparisonDTO]
    drawdown_curve: list[float]


class PortfolioAnalyticsResponseDTO(BaseModel):
    status: str = "OK"
    available_points: int = 0
    summary: RiskReturnSummaryDTO
    correlation_matrix: dict[str, dict[str, float]]
    curves: dict[str, list[dict[str, Any]]]


class HealthCheckDTO(BaseModel):
    """One health check: state, measured value, policy limits, explanation and action."""

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


class HealthPillarDTO(BaseModel):
    pillar: HealthPillar
    title: str
    status: HealthStatus
    checks: list[HealthCheckDTO]


class ConcentrationBreakdownDTO(BaseModel):
    dimension: str
    hhi: float
    effective_count: float
    weights: dict[str, float]


class InstitutionExposureDTO(BaseModel):
    issuer: str
    value_brl: float
    limit_brl: float
    usage: float


class RiskShareDTO(BaseModel):
    label: str
    weight: float
    risk_share: float


class CorrelatedPairDTO(BaseModel):
    first: str
    second: str
    correlation: float


class DiversificationDetailDTO(BaseModel):
    observations: int = 0
    shrinkage: float | None = None
    volatility: float | None = None
    diversification_ratio: float | None = None
    by_asset: list[RiskShareDTO] = Field(default_factory=list)
    by_class: list[RiskShareDTO] = Field(default_factory=list)
    correlated_pairs: list[CorrelatedPairDTO] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)


class StressResultDTO(BaseModel):
    worst_window_return: float
    window_start: date | None = None
    window_end: date | None = None
    max_drawdown: float
    observations: int


class RiskDetailDTO(BaseModel):
    observations: int = 0
    volatility: float | None = None
    current_drawdown: float | None = None
    drawdown_periods: int | None = None
    peak_date: date | None = None
    ulcer_index: float | None = None
    var_95: float | None = None
    cvar_95: float | None = None
    stress: StressResultDTO | None = None


class ConfidenceIntervalDTO(BaseModel):
    low: float
    high: float
    confidence: float = 0.95


class RollingPointDTO(BaseModel):
    end: date
    cumulative_return: float
    sharpe: float


class PerformanceDetailDTO(BaseModel):
    observations: int = 0
    cumulative_return: float | None = None
    cagr: float | None = None
    benchmark_return: float | None = None
    tracking_error: float | None = None
    information_ratio: float | None = None
    omega: float | None = None
    sharpe: float | None = None
    sharpe_interval: ConfidenceIntervalDTO | None = None
    cagr_interval: ConfidenceIntervalDTO | None = None
    cdi_consistency: float | None = None
    months_compared: int = 0
    rolling: list[RollingPointDTO] = Field(default_factory=list)
    class_returns: dict[ArcaClass, float] = Field(default_factory=dict)


class HoldingQualityDTO(BaseModel):
    ticker: str
    weight: float
    checklist_ratio: float | None = None
    stale: bool = False
    f_score: int | None = None
    z_score: float | None = None


class MaturityDTO(BaseModel):
    ticker: str
    maturity_date: date
    value_brl: float


class BracketLotDTO(BaseModel):
    ticker: str
    start_date: date
    next_bracket_date: date
    days_to_next_bracket: int
    current_rate: float
    next_rate: float
    tax_saving_by_waiting: float


class LiquidityDetailDTO(BaseModel):
    reserve_brl: float = 0.0
    reserve_months: float | None = None
    liquid_weight: float | None = None
    maturities_12m: list[MaturityDTO] = Field(default_factory=list)
    passive_income_12m_brl: float = 0.0
    exempt_weight: float | None = None
    bracket_lots: list[BracketLotDTO] = Field(default_factory=list)


class PortfolioHealthDTO(BaseModel):
    """Seven-pillar diagnosis; `pillars` come worst first and `status` is the worst one."""

    as_of_date: date
    status: HealthStatus
    total_value_brl: float
    pillars: list[HealthPillarDTO]
    concentration: list[ConcentrationBreakdownDTO] = Field(default_factory=list)
    institutions: list[InstitutionExposureDTO] = Field(default_factory=list)
    diversification: DiversificationDetailDTO = Field(default_factory=DiversificationDetailDTO)
    risk: RiskDetailDTO = Field(default_factory=RiskDetailDTO)
    performance: PerformanceDetailDTO = Field(default_factory=PerformanceDetailDTO)
    quality: list[HoldingQualityDTO] = Field(default_factory=list)
    liquidity: LiquidityDetailDTO = Field(default_factory=LiquidityDetailDTO)
