"""Pydantic request DTOs for the simulation module (Phase 33)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

BenchmarkKey = Literal["CDI", "IBOV", "IFIX", "SP500_BRL"]


class BacktestRequest(BaseModel):
    """A strategy backtest: the real contribution rules replayed over the stored history."""

    start: date
    end: date
    monthly_contribution: float = Field(gt=0, le=10_000_000)
    initial_contribution: float = Field(default=0.0, ge=0, le=100_000_000)
    correct_by_ipca: bool = False
    fee_rate: float = Field(default=0.0003, ge=0, le=0.05)
    rebalance: bool = False
    universe: Literal["REGISTERED", "REGISTERED_AND_CATALOG"] = "REGISTERED"
    # Catalog instruments added with REGISTERED_AND_CATALOG (default: the server setting).
    catalog_top: int | None = Field(default=None, ge=0, le=500)
    policy_mode: Literal["CURRENT", "AS_OF"] = "CURRENT"
    benchmarks: list[BenchmarkKey] = Field(default_factory=lambda: ["CDI", "IBOV"])
    # Also run the rule variants (bands x rebalancing) shown in the Robustness view.
    variants: bool = False
    label: str | None = Field(default=None, max_length=120)


ArcaClassKey = Literal["ACOES", "REAL_ESTATE", "ATIVOS_INTERNACIONAIS", "CAIXA"]


class ProjectionRequest(BaseModel):
    """A forward projection (layer B) from today's portfolio, in today's money.

    Leave `initial_by_class` and `income_yield_by_class` empty to start from the portfolio
    as it is today, and `cdi_rate`/`ipca_rate` empty to use the policy premises (or, without
    them, the current market rates).
    """

    horizon_years: int = Field(default=20, ge=1, le=50)
    monthly_contribution: float = Field(ge=0, le=10_000_000)
    contribution_real_growth: float = Field(default=0.0, ge=-0.2, le=0.2)
    initial_by_class: dict[ArcaClassKey, float] | None = None
    income_yield_by_class: dict[ArcaClassKey, float] | None = None
    cdi_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    ipca_rate: float | None = Field(default=None, ge=-0.2, le=1.0)
    wealth_goal: float | None = Field(default=None, gt=0)
    income_goal: float | None = Field(default=None, gt=0)
    rebalance: bool = False
    paths: int = Field(default=5000, ge=100, le=5000)
    mean_block_months: float = Field(default=12.0, ge=3.0, le=24.0)
    fee_rate: float = Field(default=0.0003, ge=0, le=0.05)
    sample_start: date | None = None
    # STACKED: the calibrated mixture of generators; or one generator alone.
    generator: Literal["STACKED", "BOOTSTRAP", "BAYESIAN_BOOTSTRAP", "BAYESIAN_NORMAL"] = "STACKED"
    label: str | None = Field(default=None, max_length=120)


class CandidatesRequest(ProjectionRequest):
    """Candidates outside the portfolio (layer D), measured on the projection paths.

    The watchlist always enters; the screener adds the most traded catalog instruments. The
    same filters as the real contribution apply (eligibility, suspicious data), up to 20.
    """

    horizon_years: int = Field(default=5, ge=1, le=30)
    monthly_contribution: float = Field(default=0.0, ge=0, le=10_000_000)
    paths: int = Field(default=2000, ge=100, le=5000)
    include_screener: bool = True
    screener_min_volume: float = Field(default=1_000_000.0, ge=0)
    include_ineligible: bool = False
    include_suspicious: bool = False
    # NEXT_CONTRIBUTION: an equal share of its class; FIXED: `fixed_weight` of the portfolio.
    weight_mode: Literal["NEXT_CONTRIBUTION", "FIXED"] = "NEXT_CONTRIBUTION"
    fixed_weight: float = Field(default=0.05, gt=0, le=0.5)
    # Loss on the rupture event: 55% (central) or 90% (stress, design 10.4).
    rupture_stress: bool = False
