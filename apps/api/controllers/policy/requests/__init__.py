"""Pydantic request/response DTOs for the policy module.

Scope: versioned investment policy and ARCA targets.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from domain.shared.enums import (
    ArcaClass,
    IntraClassStrategy,
)


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
    projected_cdi_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    projected_ipca_rate: float | None = Field(default=None, ge=-0.5, le=1.0)
    scenario_rate_shift: float = Field(default=0.02, ge=0.0, le=0.5)


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


class HealthPolicyDTO(BaseModel):
    """Limits of the portfolio health diagnosis; fractions follow ADR 0006 (0.15 = 15%)."""

    max_asset_weight_warning: float = Field(default=0.15, ge=0.0, le=1.0)
    max_asset_weight_critical: float = Field(default=0.25, ge=0.0, le=1.0)
    max_top5_weight_warning: float = Field(default=0.60, ge=0.0, le=1.0)
    max_top5_weight_critical: float = Field(default=0.80, ge=0.0, le=1.0)
    max_sector_weight_warning: float = Field(default=0.30, ge=0.0, le=1.0)
    max_sector_weight_critical: float = Field(default=0.45, ge=0.0, le=1.0)
    min_effective_assets_warning: float = Field(default=8.0, ge=0.0)
    min_effective_assets_critical: float = Field(default=4.0, ge=0.0)
    fgc_limit_brl: float = Field(default=250_000.0, gt=0.0)
    fgc_warning_ratio: float = Field(default=0.90, ge=0.0, le=1.0)
    min_diversification_ratio_warning: float = Field(default=1.20, ge=0.0)
    min_diversification_ratio_critical: float = Field(default=1.05, ge=0.0)
    high_correlation: float = Field(default=0.80, ge=0.0, le=1.0)
    max_asset_risk_share: float = Field(default=0.25, ge=0.0, le=1.0)
    max_volatility_warning: float = Field(default=0.15, ge=0.0, le=5.0)
    max_volatility_critical: float = Field(default=0.25, ge=0.0, le=5.0)
    max_drawdown_warning: float = Field(default=0.10, ge=0.0, le=1.0)
    max_drawdown_critical: float = Field(default=0.20, ge=0.0, le=1.0)
    max_stress_loss_warning: float = Field(default=0.10, ge=0.0, le=1.0)
    max_stress_loss_critical: float = Field(default=0.20, ge=0.0, le=1.0)
    min_cdi_consistency: float = Field(default=0.50, ge=0.0, le=1.0)
    min_checklist_quality_warning: float = Field(default=0.50, ge=-1.0, le=1.0)
    min_checklist_quality_critical: float = Field(default=0.0, ge=-1.0, le=1.0)
    checklist_max_age_months: int = Field(default=12, ge=1, le=120)
    max_stale_checklist_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    monthly_expenses_brl: float | None = Field(default=None, gt=0.0)
    min_reserve_months_warning: float = Field(default=6.0, ge=0.0)
    min_reserve_months_critical: float = Field(default=3.0, ge=0.0)
    min_liquid_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    bracket_window_days: int = Field(default=30, ge=1, le=365)
    min_observations: int = Field(default=60, ge=2, le=2520)


class PolicyUpdateRequest(BaseModel):
    """Full policy; saving it creates a new version (ADR 0005)."""

    arca: list[ClassPolicyDTO]
    eligibility: EligibilityPolicyDTO = Field(default_factory=EligibilityPolicyDTO)
    valuation: ValuationPolicyDTO = Field(default_factory=ValuationPolicyDTO)
    health: HealthPolicyDTO = Field(default_factory=HealthPolicyDTO)


class PolicyDTO(PolicyUpdateRequest):
    version: int | None = None
    created_at: datetime | None = None
