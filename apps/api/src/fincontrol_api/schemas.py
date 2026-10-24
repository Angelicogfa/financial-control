"""Pydantic v2 request and response DTOs for the FastAPI HTTP controllers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fincontrol_core.domain.enums import (
    ArcaClass,
    AssetType,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
    IntraClassStrategy,
    TransactionKind,
)
from fincontrol_core.market.models import QuoteFreshness
from pydantic import BaseModel, ConfigDict, Field


class PageMetaDTO(BaseModel):
    """Standardized pagination metadata."""

    model_config = ConfigDict(from_attributes=True)

    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool
    sort_by: str
    sort_order: str


class PaginatedResponse[T](BaseModel):
    """Standardized paginated response envelope for all listing endpoints."""

    items: list[T]
    meta: PageMetaDTO


class FixedIncomeTermPayload(BaseModel):
    """Contract parameters for fixed income and treasury assets."""

    instrument_kind: FixedIncomeInstrumentKind
    indexer: FixedIncomeIndexer
    contracted_rate: Decimal = Field(
        ...,
        description=(
            "ADR 0006: multiplier for CDI/SELIC (1.10 = 110% of CDI); "
            "annual fraction for PRE/IPCA (0.065 = 6.5% a.a.)"
        ),
    )
    issue_date: date
    maturity_date: date | None = None
    tax_exempt: bool = False
    liquidity: FixedIncomeLiquidity = FixedIncomeLiquidity.AT_MATURITY
    issuer: str | None = None


class AssetCreateRequest(BaseModel):
    """Payload to register a new investment asset."""

    ticker: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=160)
    asset_type: AssetType
    arca_class: ArcaClass | None = None
    currency: str | None = None
    manual_price: Decimal | None = Field(default=None, ge=Decimal("0"))
    custom_class_weight: Decimal | None = Field(default=None, ge=Decimal("0"))
    use_cerrado: bool = True
    cerrado_answers: dict[str, bool] = Field(default_factory=dict)
    notes: str | None = None
    fixed_income_term: FixedIncomeTermPayload | None = None


class AssetUpdateRequest(BaseModel):
    """Payload to update an existing investment asset."""

    ticker: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    asset_type: AssetType | None = None
    arca_class: ArcaClass | None = None
    currency: str | None = None
    manual_price: Decimal | None = Field(default=None, ge=Decimal("0"))
    custom_class_weight: Decimal | None = Field(default=None, ge=Decimal("0"))
    use_cerrado: bool | None = None
    cerrado_answers: dict[str, bool] | None = None
    is_active: bool | None = None
    notes: str | None = None
    fixed_income_term: FixedIncomeTermPayload | None = None


class CerradoUpdateRequest(BaseModel):
    """Payload to toggle Diagrama do Cerrado or update answers/manual weight on an asset."""

    use_cerrado: bool = True
    cerrado_answers: dict[str, bool] = Field(default_factory=dict)
    custom_class_weight: Decimal | None = Field(default=None, ge=Decimal("0"))


class AssetResponseDTO(BaseModel):
    """Serialized Asset domain entity."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name: str
    asset_type: AssetType
    arca_class: ArcaClass
    currency: str
    manual_price: Decimal | None = None
    custom_class_weight: Decimal | None = None
    use_cerrado: bool
    cerrado_answers: dict[str, bool]
    is_active: bool
    notes: str | None = None
    fixed_income_term: FixedIncomeTermPayload | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TransactionCreateRequest(BaseModel):
    """Payload to record a buy or sell trade."""

    asset_id: int
    kind: TransactionKind
    trade_date: date
    quantity: Decimal = Field(..., gt=Decimal("0"))
    unit_price: Decimal = Field(..., ge=Decimal("0"))
    fees: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    fx_rate: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    notes: str | None = None


class TransactionUpdateRequest(BaseModel):
    """Payload to correct a recorded trade (the asset cannot change)."""

    kind: TransactionKind
    trade_date: date
    quantity: Decimal = Field(..., gt=Decimal("0"))
    unit_price: Decimal = Field(..., ge=Decimal("0"))
    fees: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    fx_rate: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    notes: str | None = None


class TransactionResponseDTO(BaseModel):
    """Serialized Transaction domain entity."""

    id: int
    asset_id: int
    ticker: str | None = None
    kind: TransactionKind
    trade_date: date
    quantity: float
    unit_price: float
    fees: float
    fx_rate: float
    total_brl: float
    notes: str | None = None
    created_at: datetime | None = None


class EarningCreateRequest(BaseModel):
    """Payload to record received dividends, JCP, FII yields, or fixed income coupons."""

    asset_id: int
    kind: EarningKind
    payment_date: date
    gross_amount: Decimal = Field(..., gt=Decimal("0"))
    withholding_tax: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    net_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    ex_date: date | None = None
    notes: str | None = None
    fx_rate: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))


class EarningUpdateRequest(BaseModel):
    """Payload to correct a recorded earning (the asset cannot change)."""

    kind: EarningKind
    payment_date: date
    gross_amount: Decimal = Field(..., gt=Decimal("0"))
    withholding_tax: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    net_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    ex_date: date | None = None
    notes: str | None = None
    fx_rate: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))


class EarningResponseDTO(BaseModel):
    """Serialized Earning domain entity."""

    id: int
    asset_id: int
    ticker: str | None = None
    kind: EarningKind
    payment_date: date
    ex_date: date | None = None
    gross_amount: float
    withholding_tax: float
    net_amount: float
    fx_rate: float = 1.0
    net_amount_brl: float = 0.0
    notes: str | None = None
    created_at: datetime | None = None


class EvaluatedAnswerDTO(BaseModel):
    question_id: str
    text: str
    category: str
    hint: str
    answer: bool | None
    source: str
    automatable: bool


class CerradoEvaluationDTO(BaseModel):
    asset_type: AssetType
    use_cerrado: bool
    score: int
    max_score: int
    answered: int
    pending: int
    recommendation: str
    answers: list[EvaluatedAnswerDTO]


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
    projection_assumptions: dict[str, float] = Field(default_factory=dict)


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


class ArcaTargetItemDTO(BaseModel):
    arca_class: ArcaClass
    target_pct: float = Field(..., ge=0.0, le=100.0)
    intra_class_strategy: IntraClassStrategy = IntraClassStrategy.CERRADO


class ArcaTargetsUpdateRequest(BaseModel):
    targets: list[ArcaTargetItemDTO]


class BenchmarkComparisonDTO(BaseModel):
    benchmark: str
    benchmark_return: float
    excess_return: float
    beta: float | None = None
    alpha_annual: float | None = None
    correlation: float | None = None


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


class AssetAnalysisResponseDTO(BaseModel):
    asset: AssetResponseDTO
    position: ValuedPositionDTO | None = None
    fundamentals: dict[str, Any] | None = None
    valuation: dict[str, Any]
    cerrado: CerradoEvaluationDTO
    risk_return: RiskReturnSummaryDTO
    price_history: list[dict[str, Any]]
