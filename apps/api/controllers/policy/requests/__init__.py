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
