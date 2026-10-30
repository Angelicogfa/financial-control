"""Pydantic response DTOs for the assets module.

Scope: asset registry, checklist and fundamentalist analysis.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from controllers.assets.requests import AnswerInput, FixedIncomeTermPayload
from controllers.portfolio.responses import RiskReturnSummaryDTO, ValuedPositionDTO
from controllers.shared.responses import CerradoEvaluationDTO
from domain.shared.enums import (
    AnswerSource,
    AnswerValue,
    ArcaClass,
    AssetLifecycle,
    AssetPurpose,
    AssetType,
    ChecklistProfile,
)


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
    suspicious_inputs: list[str] = Field(default_factory=list)
    extraordinary_dividends: bool = False


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


class IndicatorRatingDTO(BaseModel):
    """Whether an indicator is good, and against what (the strategy's own references)."""

    status: Literal["GOOD", "CAUTION", "BAD", "SUSPICIOUS"]
    reference: str


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
    # By indicator key (fundamentals and history), e.g. "price_to_earnings", "roe_average".
    indicator_ratings: dict[str, IndicatorRatingDTO] = Field(default_factory=dict)


PriceRange = Literal["6mo", "1y", "2y", "5y", "max"]


class PricePointDTO(BaseModel):
    date: date
    close: float


class DatedPriceDTO(BaseModel):
    date: date
    price: float


class AssetPriceHistoryDTO(BaseModel):
    """Closes of one period for the chart (at most 500 points) and its summary."""

    range: PriceRange
    points: list[PricePointDTO]
    change: float | None = None
    high: DatedPriceDTO | None = None
    low: DatedPriceDTO | None = None
    dropped_spikes: int = 0


class ForecastProbabilityDTO(BaseModel):
    value: float
    low: float
    high: float


class ForecastThresholdDTO(BaseModel):
    """A price that matters and the chance of being past it at the horizon."""

    key: Literal["NOW", "AVERAGE", "FAIR", "FALL_20"]
    label: str
    price: float
    direction: Literal["above", "below"]
    probability: float


class ForecastHorizonDTO(BaseModel):
    months: int
    target_date: date
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float
    total_return_p50: float
    up: ForecastProbabilityDTO
    fall_20: ForecastProbabilityDTO
    thresholds: list[ForecastThresholdDTO] = Field(default_factory=list)
    # 99 price quantiles (1% to 99%): any "chance of passing R$ X" is read from them.
    price_quantiles: list[float] = Field(default_factory=list)


class ForecastDriverDTO(BaseModel):
    key: Literal["MARKET", "OWN", "VALUATION", "EVENTS"]
    label: str
    annual: float | None = None
    note: str = ""


class ForecastEventDTO(BaseModel):
    """A CVM event of the last 20 trading days and what it adds to the forecast (Phase 42.5)."""

    event_class: str
    label: str
    event_date: date
    days_after: int  # trading days since the delivery
    effect: float  # abnormal return still to come in the first month (0 when not used)
    used: bool  # its class passed the out-of-sample gate
    note: str


class ForecastSealDTO(BaseModel):
    level: int
    label: str
    text: str


class AssetForecastDTO(BaseModel):
    """Probabilistic price forecast of an asset (Phase 42): a distribution, not a target."""

    asset_id: int
    ticker: str
    status: Literal["OK", "INSUFFICIENT_HISTORY", "NOT_COMPUTED", "LOW_CONFIDENCE"]
    as_of: date | None = None
    price_now: float | None = None
    lead: str | None = None
    months_used: int | None = None
    beta: float | None = None
    alpha_annual: float | None = None
    shrinkage: float | None = None
    dividend_yield_annual: float | None = None
    expected_total_return_annual: float | None = None
    horizons: list[ForecastHorizonDTO] = Field(default_factory=list)
    drivers: list[ForecastDriverDTO] = Field(default_factory=list)
    recent_events: list[ForecastEventDTO] = Field(default_factory=list)
    seal: ForecastSealDTO | None = None
    requested: bool = False  # asked for by the user: shown with a warning, from 12 months
    cautions: list[str] = Field(default_factory=list)  # why to read it with care
    warnings: list[str] = Field(default_factory=list)
    model_version: str | None = None


class ValuationOriginDTO(BaseModel):
    origin: str
    mse_model: float
    mse_zero: float
    observations: int


class ForecastValuationDTO(BaseModel):
    """Layer B (42.3): what the valuation said about the next 12 months, and if it is used."""

    as_of: date
    passed: bool
    reason: str
    gamma_annual_per_z: float  # extra return a year per unit of z (estimate, before the gate)
    gamma_used_annual_per_z: float
    sign_probability: float
    months: int
    companies: int
    oos_improvement: float
    oos_win_share: float
    origins: list[ValuationOriginDTO] = Field(default_factory=list)


class ForecastQualityDTO(BaseModel):
    """How often the forecast bands held in a rolling-origin backtest."""

    status: Literal["OK", "NOT_COMPUTED"]
    as_of: date | None = None
    horizon_months: int | None = None
    windows: int = 0
    effective_windows: float = 0.0
    assets: int = 0
    coverage_50: float | None = None
    coverage_90: float | None = None
    mean_pit: float | None = None
    brier: float | None = None
    brier_reference: float | None = None
    first_origin: date | None = None
    last_origin: date | None = None
    seal: ForecastSealDTO | None = None
    valuation: ForecastValuationDTO | None = None
