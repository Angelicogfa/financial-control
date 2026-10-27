"""Pydantic request/response DTOs for the assets module.

Scope: asset registry, checklist and fundamentalist analysis.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
)

# A checklist answer: YES/NO/NA, a legacy boolean, or None (pending).
AnswerInput = AnswerValue | bool | None


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
    issue_date: date | None = Field(
        default=None,
        description="Informational only: every purchase accrues from its own trade date",
    )
    maturity_date: date | None = None
    tax_exempt: bool = False
    liquidity: FixedIncomeLiquidity = FixedIncomeLiquidity.AT_MATURITY
    issuer: str | None = None
    semiannual_coupons: bool = Field(
        default=False,
        description="Pays semiannual coupons (Juros Semestrais); no implied rate from the price",
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
