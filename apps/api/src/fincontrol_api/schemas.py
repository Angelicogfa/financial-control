"""Pydantic v2 request and response DTOs for the FastAPI HTTP controllers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fincontrol_core.domain.enums import (
    AccountKind,
    AnswerSource,
    AnswerValue,
    ArcaClass,
    AssetLifecycle,
    AssetPurpose,
    AssetType,
    ChecklistProfile,
    ContributionPlanStatus,
    CorporateEventKind,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
    IntraClassStrategy,
    SeriesUnit,
    TransactionKind,
)
from fincontrol_core.market.models import QuoteFreshness
from pydantic import BaseModel, ConfigDict, Field

# A checklist answer: YES/NO/NA, a legacy boolean, or None (pending).
AnswerInput = AnswerValue | bool | None


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

    ticker: str | None = Field(
        default=None,
        min_length=1,
        max_length=32,
        description="Required for exchange-traded assets; generated for fixed income and cash",
    )
    name: str = Field(..., min_length=1, max_length=160)
    asset_type: AssetType
    arca_class: ArcaClass | None = None
    currency: str | None = None
    manual_price: Decimal | None = Field(default=None, ge=Decimal("0"))
    custom_class_weight: Decimal | None = Field(default=None, ge=Decimal("0"))
    use_cerrado: bool = True
    cerrado_answers: dict[str, AnswerInput] = Field(default_factory=dict)
    checklist_profile: ChecklistProfile | None = None
    notes: str | None = None
    purpose: AssetPurpose = AssetPurpose.ARCA
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
    cerrado_answers: dict[str, AnswerInput] | None = None
    checklist_profile: ChecklistProfile | None = None
    is_active: bool | None = None
    notes: str | None = None
    purpose: AssetPurpose | None = None
    fixed_income_term: FixedIncomeTermPayload | None = None


class AccountRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    institution: str | None = Field(default=None, max_length=120)
    kind: AccountKind = AccountKind.BROKER
    is_active: bool = True


class AccountDTO(AccountRequest):
    id: int
    created_at: datetime | None = None


class ArcaSuggestionDTO(BaseModel):
    """Suggested ARCA class by economic exposure (catalog) or by asset type."""

    ticker: str
    asset_type: AssetType
    arca_class: ArcaClass
    source: str
    reason: str


class CerradoUpdateRequest(BaseModel):
    """Toggle the checklist, set its profile, answers (YES/NO/NA) with evidence, manual weight.

    `cerrado_answers` is the full set of manual answers: questions left out become pending.
    """

    use_cerrado: bool = True
    cerrado_answers: dict[str, AnswerInput] = Field(default_factory=dict)
    evidence: dict[str, str] = Field(default_factory=dict)
    checklist_profile: ChecklistProfile | None = None
    custom_class_weight: Decimal | None = Field(default=None, ge=Decimal("0"))


class ChecklistAnswerDTO(BaseModel):
    value: AnswerValue | None
    source: AnswerSource
    evidence: str | None = None
    answered_at: datetime | None = None
    checklist_version: int = 2


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
    # YES/NO answers as booleans (NA omitted); `checklist_answers` carries the full record.
    cerrado_answers: dict[str, bool]
    checklist_profile: ChecklistProfile
    checklist_answers: dict[str, ChecklistAnswerDTO] = Field(default_factory=dict)
    is_active: bool
    notes: str | None = None
    purpose: AssetPurpose = AssetPurpose.ARCA
    lifecycle_status: AssetLifecycle | None = None
    eligible: bool | None = None
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
    account_id: int | None = None


class TransactionUpdateRequest(BaseModel):
    """Payload to correct a recorded trade (the asset cannot change)."""

    kind: TransactionKind
    trade_date: date
    quantity: Decimal = Field(..., gt=Decimal("0"))
    unit_price: Decimal = Field(..., ge=Decimal("0"))
    fees: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    fx_rate: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    notes: str | None = None
    account_id: int | None = None


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
    account_id: int | None = None
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
    account_id: int | None = None


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
    account_id: int | None = None


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
    account_id: int | None = None
    created_at: datetime | None = None


class EvaluatedAnswerDTO(BaseModel):
    question_id: str
    text: str
    category: str
    hint: str
    value: AnswerValue | None
    answer: bool | None
    source: str
    automatable: bool
    evidence: str | None = None
    answered_at: datetime | None = None


class CerradoEvaluationDTO(BaseModel):
    profile: ChecklistProfile
    checklist_version: int
    use_cerrado: bool
    score: int
    max_score: int
    normalized_score: float | None
    coverage_pct: float
    answered: int
    applicable: int
    not_applicable: int
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
    projection_assumptions: dict[str, float] = Field(default_factory=dict)
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


class ImportLineDTO(BaseModel):
    line_no: int
    action: str
    status: str
    entry_date: date | None = None
    ticker: str | None = None
    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    trade_kind: str | None = None
    earning_kind: str | None = None
    event_kind: str | None = None
    note: str = ""


class UnknownTickerDTO(BaseModel):
    ticker: str
    name: str | None = None
    asset_type: AssetType | None = None


class ImportPreviewDTO(BaseModel):
    kind: str
    counts: dict[str, int]
    unknown_tickers: list[UnknownTickerDTO]
    lines: list[ImportLineDTO]


class ImportCommitDTO(BaseModel):
    kind: str
    created: dict[str, int]
    skipped: dict[str, int]
    created_assets: list[str] = Field(default_factory=list)


class CorporateEventRequest(BaseModel):
    """Split (factor 2 for 1:2), reverse split (0.1 for 10:1) or bonus (1.1 for 10%)."""

    asset_id: int
    kind: CorporateEventKind
    ex_date: date
    factor: Decimal = Field(..., gt=Decimal("0"))
    unit_cost: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    notes: str | None = None


class CorporateEventDTO(CorporateEventRequest):
    id: int
    ticker: str | None = None
    imported: bool = False


class ExecutionDTO(BaseModel):
    """What was bought for one asset of the plan; price in the asset currency."""

    asset_id: int
    quantity: Decimal = Field(..., gt=Decimal("0"))
    unit_price: Decimal = Field(..., ge=Decimal("0"))
    fees: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    fx_rate: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))


class ContributionConfirmRequest(BaseModel):
    """Confirm a draft: without `executions`, the suggested quantities and prices are used."""

    trade_date: date
    account_id: int | None = None
    executions: list[ExecutionDTO] | None = None


class SavedContributionPlanDTO(BaseModel):
    id: int
    status: ContributionPlanStatus
    created_at: datetime | None = None
    confirmed_at: datetime | None = None
    discarded_at: datetime | None = None
    strategy_override: IntraClassStrategy | None = None
    policy_version: int | None = None
    account_id: int | None = None
    transaction_ids: list[int] = Field(default_factory=list)
    plan: ContributionPlanResponseDTO


class ArcaTargetItemDTO(BaseModel):
    arca_class: ArcaClass
    target_pct: float = Field(..., ge=0.0, le=100.0)
    intra_class_strategy: IntraClassStrategy = IntraClassStrategy.CERRADO


class ArcaTargetsUpdateRequest(BaseModel):
    targets: list[ArcaTargetItemDTO]


class ClassPolicyDTO(BaseModel):
    arca_class: ArcaClass
    target_pct: float = Field(..., ge=0.0, le=100.0)
    band_pct: float = Field(default=5.0, ge=0.0, le=50.0)
    intra_class_strategy: IntraClassStrategy = IntraClassStrategy.CERRADO


class EligibilityPolicyDTO(BaseModel):
    require_evaluation: bool = False
    min_score: int = 1
    min_coverage_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class ProjectionAssumptionsDTO(BaseModel):
    equity_capital_growth_rate: float = 0.08
    fund_capital_growth_rate: float = 0.10
    real_estate_default_yield_rate: float = 0.085
    cash_cdi_multiplier: float = 1.0
    cash_income_tax_rate: float = 0.175


class ValuationPolicyDTO(BaseModel):
    bazin_required_yield: float = 0.06
    graham_multiplier: float = 22.5
    max_price_to_earnings: float = 15.0
    max_ev_to_ebitda: float = 10.0
    max_price_to_book_bank: float = 2.0
    bank_cost_of_equity: float = 0.14
    max_price_to_book_fii: float = 1.05
    reference_real_yield: float = 0.06
    min_fii_spread: float = 0.02
    min_margin_of_safety: float = 0.15
    projections: ProjectionAssumptionsDTO = Field(default_factory=ProjectionAssumptionsDTO)


class PolicyUpdateRequest(BaseModel):
    """Full policy; saving it creates a new version (ADR 0005)."""

    arca: list[ClassPolicyDTO]
    eligibility: EligibilityPolicyDTO = Field(default_factory=EligibilityPolicyDTO)
    valuation: ValuationPolicyDTO = Field(default_factory=ValuationPolicyDTO)


class PolicyDTO(PolicyUpdateRequest):
    version: int | None = None
    created_at: datetime | None = None


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


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=1, max_length=256)


class CurrentUserDTO(BaseModel):
    username: str
    expires_at: datetime | None = None


class ReadinessCheckDTO(BaseModel):
    ok: bool
    detail: str


class ReadinessDTO(BaseModel):
    """Readiness of the API: `ready`, `degraded` (cache down) or `not_ready`."""

    status: str
    checks: dict[str, ReadinessCheckDTO]


class JobRunDTO(BaseModel):
    """Latest execution of a background job."""

    job_name: str
    status: str
    attempts: int
    started_at: datetime
    finished_at: datetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class SeriesStatusDTO(BaseModel):
    """Freshness diagnostics of a persisted market or macro series."""

    symbol: str
    unit: SeriesUnit | None = None
    points: int
    first_date: date | None = None
    last_date: date | None = None
    stale: bool
    missing_business_days: int


class MethodResultDTO(BaseModel):
    method: str
    label: str
    kind: str
    value: float | None = None
    threshold: float | None = None
    passes: bool | None = None
    margin: float | None = None
    note: str = ""


class AssetValuationDTO(BaseModel):
    profile: ChecklistProfile
    applicable: bool
    price: float | None = None
    methods: list[MethodResultDTO]
    fair_value: float | None = None
    margin: float | None = None
    verdict: str
    reason: str = ""


class FundamentalSnapshotDTO(BaseModel):
    reference_date: date
    period: str
    metrics: dict[str, float | None]
    source: str | None = None


class HistoricalMetricsDTO(BaseModel):
    years: int
    first_year: int | None = None
    last_year: int | None = None
    roe_average: float | None = None
    revenue_cagr: float | None = None
    earnings_cagr: float | None = None
    profitable_years: int
    dividend_years: int
    payout_average: float | None = None
    always_profitable: bool
    dividend_regularity: float | None = None


class ChecklistEvaluationRecordDTO(BaseModel):
    evaluated_at: datetime
    profile: ChecklistProfile
    checklist_version: int
    score: int
    normalized_score: float | None = None
    coverage_pct: float
    answered: int
    applicable: int
    recommendation: str


class ChecklistAnswerHistoryDTO(ChecklistAnswerDTO):
    question_id: str


class AssetAnalysisResponseDTO(BaseModel):
    """Everything about one asset: position, fundamentals over time, valuation, checklist."""

    asset: AssetResponseDTO
    position: ValuedPositionDTO | None = None
    fundamentals: dict[str, Any] | None = None
    fundamental_history: list[FundamentalSnapshotDTO] = Field(default_factory=list)
    historical_metrics: HistoricalMetricsDTO | None = None
    valuation: AssetValuationDTO
    checklist: CerradoEvaluationDTO
    checklist_history: list[ChecklistEvaluationRecordDTO] = Field(default_factory=list)
    answer_history: list[ChecklistAnswerHistoryDTO] = Field(default_factory=list)
    risk_return: RiskReturnSummaryDTO
    benchmark: str
    price_history: list[dict[str, Any]]


class ScreenerItemDTO(BaseModel):
    ticker: str
    name: str
    asset_type: AssetType
    arca_class: ArcaClass
    sector: str | None = None
    close: float | None = None
    change_pct: float | None = None
    volume_brl: float | None = None
    market_cap: float | None = None
    logo_url: str | None = None
    price_to_earnings: float | None = None
    price_to_book: float | None = None
    dividend_yield: float | None = None
    return_on_equity: float | None = None
    valuation_verdict: str | None = None
    fair_value: float | None = None
    margin: float | None = None
    asset_id: int | None = None
    lifecycle_status: AssetLifecycle | None = None


class ScreenerResponseDTO(BaseModel):
    results: list[ScreenerItemDTO]
    candidates: int
    scanned: int
    truncated: bool
    arca_classes: list[ArcaClass] = Field(default_factory=list)
    catalog_size: int
    catalog_updated_at: datetime | None = None


class WatchlistAddRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=32)
    asset_type: AssetType | None = None
    name: str | None = Field(default=None, max_length=160)


class WatchlistItemDTO(BaseModel):
    asset_id: int
    ticker: str
    name: str
    asset_type: AssetType
    arca_class: ArcaClass
    lifecycle_status: AssetLifecycle
    eligible: bool
    price: float | None = None
    change_pct: float | None = None
    checklist_profile: ChecklistProfile
    checklist_score: int
    checklist_normalized_score: float | None = None
    checklist_coverage_pct: float
    checklist_recommendation: str
    valuation_verdict: str
    fair_value: float | None = None
    margin: float | None = None
