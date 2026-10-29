"""Pydantic response DTOs for the simulation module (Phase 33)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from domain.simulation.data import CoverageStatus
from domain.simulation.entities import SimulationKind, SimulationStatus


class SeriesCoverageDTO(BaseModel):
    key: str
    label: str
    status: CoverageStatus
    first_date: date | None = None
    last_date: date | None = None
    points: int = 0
    months_expected: int = 0
    months_covered: int = 0
    share: float = 0.0
    longest_gap_days: int = 0
    note: str | None = None


class CoverageReportDTO(BaseModel):
    """Which stored series cover the simulation period (`missing`: no point at all)."""

    start: date
    end: date
    series: list[SeriesCoverageDTO] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class SimulationRunDTO(BaseModel):
    """A requested simulation and what makes it reproducible (params, data and code hashes)."""

    id: int
    kind: SimulationKind
    status: SimulationStatus
    label: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    params_hash: str
    data_hash: str | None = None
    code_version: str
    seed: int
    error: str | None = None
    reused_from: int | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class BacktestPointDTO(BaseModel):
    day: date
    contribution: float
    contributed: float
    market_value: float
    cash: float
    fees: float
    taxes: float = 0.0
    by_class: dict[str, float] = Field(default_factory=dict)


class BacktestSummaryDTO(BaseModel):
    final_value: float
    contributed: float
    gain: float
    money_weighted_return: float | None = None
    time_weighted_return: float
    annual_twr: float
    volatility: float
    max_drawdown: float
    trades: int
    fees: float
    taxes: float = 0.0
    sales: int = 0


class SimulationResultDTO(BaseModel):
    """One series of a run: `strategy` or `benchmark:<KEY>`."""

    key: str
    label: str
    summary: BacktestSummaryDTO
    points: list[BacktestPointDTO] = Field(default_factory=list)
    unavailable: list[str] = Field(default_factory=list)
    survivorship_bias: bool = False


class SimulationRunDetailDTO(SimulationRunDTO):
    results: list[SimulationResultDTO] = Field(default_factory=list)


class WindowOutcomeDTO(BaseModel):
    """Return (contributions removed) and drawdown of one series inside a window."""

    covered: bool
    months: int = 0
    return_rate: float | None = None
    max_drawdown: float | None = None


class SeriesRefDTO(BaseModel):
    key: str
    label: str


class CrisisDTO(BaseModel):
    key: str
    label: str
    start: date
    end: date
    # By series key (`strategy`, `benchmark:IBOV`, ...).
    outcomes: dict[str, WindowOutcomeDTO] = Field(default_factory=dict)


class ShockDTO(BaseModel):
    """First-order effect of an instant shock on the final allocation."""

    key: str
    label: str
    before: float
    after: float
    change: float
    change_rate: float
    by_class: dict[str, float] = Field(default_factory=dict)
    note: str = ""


class VariantDTO(BaseModel):
    key: str
    label: str
    band_pct: float
    rebalance: bool
    summary: BacktestSummaryDTO
    # Before the reserved window (where a rule may be chosen) and inside it (validation only).
    selection: WindowOutcomeDTO
    holdout: WindowOutcomeDTO


class DistributionDTO(BaseModel):
    count: int
    minimum: float | None = None
    median: float | None = None
    maximum: float | None = None


class VariantValidationDTO(BaseModel):
    """Phase 33.8: is the best rule variant better for real, or the luckiest of the trials?"""

    best: str
    best_label: str
    best_sharpe_annual: float
    expected_max_sharpe_annual: float
    deflated_probability: float
    trials: int
    observations: int
    pbo: float | None = None
    pbo_combinations: int = 0
    gate_probability: float | None = None
    passed: bool
    verdict: str
    notes: list[str] = Field(default_factory=list)


class RobustnessDTO(BaseModel):
    run_id: int
    status: SimulationStatus
    series: list[SeriesRefDTO] = Field(default_factory=list)
    crises: list[CrisisDTO] = Field(default_factory=list)
    shocks: list[ShockDTO] = Field(default_factory=list)
    variants: list[VariantDTO] = Field(default_factory=list)
    # Distribution over every variant of this run (never only the best one).
    annual_twr_distribution: DistributionDTO
    selection_distribution: DistributionDTO
    holdout_distribution: DistributionDTO
    holdout_start: date | None = None
    # Variants computed in this run and in every computed run so far (risk R3).
    trials_in_run: int = 0
    trials_total: int = 0
    warnings: list[str] = Field(default_factory=list)
    validation: VariantValidationDTO | None = None


class PercentilesDTO(BaseModel):
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float


class GoalOutcomeDTO(BaseModel):
    target: float
    probability: float
    standard_error: float  # Monte Carlo only
    months: PercentilesDTO | None = None
    # 90% credibility interval: finite paths plus the spread between generators (33.6).
    low: float = 0.0
    high: float = 1.0
    by_generator: dict[str, float] = Field(default_factory=dict)


class EventOutcomeDTO(BaseModel):
    key: str
    label: str
    probability: float
    standard_error: float
    low: float
    high: float
    by_generator: dict[str, float] = Field(default_factory=dict)


class GeneratorShareDTO(BaseModel):
    key: str
    label: str
    weight: float
    paths: int


class ProjectionPointDTO(BaseModel):
    month: int
    contributed: float
    wealth: PercentilesDTO
    income: PercentilesDTO


class ClassPremiseDTO(BaseModel):
    arca_class: str
    proxy: str
    excess_annual: float
    volatility: float
    expected_annual: float
    income_yield: float
    prior_excess_annual: float | None = None
    posterior_excess_annual: float | None = None


class RateScenarioDTO(BaseModel):
    name: str
    annual_cdi_rate: float
    annual_ipca_rate: float


class ProjectionScenarioDTO(BaseModel):
    """One rate scenario; amounts are in today's money (deflated by the scenario IPCA)."""

    key: str
    label: str
    scenario: RateScenarioDTO
    paths: int
    horizon_months: int
    points: list[ProjectionPointDTO] = Field(default_factory=list)
    final_wealth: PercentilesDTO
    final_net_wealth: PercentilesDTO
    final_income: PercentilesDTO
    max_drawdown: PercentilesDTO
    contributed: float
    wealth_goal: GoalOutcomeDTO | None = None
    income_goal: GoalOutcomeDTO | None = None
    premises: list[ClassPremiseDTO] = Field(default_factory=list)
    fees: float = 0.0
    taxes: float = 0.0
    events: list[EventOutcomeDTO] = Field(default_factory=list)
    generators: list[GeneratorShareDTO] = Field(default_factory=list)
    prior_months: float | None = None


class ProjectionDTO(BaseModel):
    run_id: int
    status: SimulationStatus
    scenarios: list[ProjectionScenarioDTO] = Field(default_factory=list)
    sample_start: date | None = None
    sample_end: date | None = None
    sample_months: int = 0
    classes: list[str] = Field(default_factory=list)
    targets: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    calibration_run: int | None = None


CalibrationStatusKey = Literal["CALIBRATED", "MISCALIBRATED", "INCONCLUSIVE"]


class GeneratorCalibrationDTO(BaseModel):
    key: str
    label: str
    weight: float
    windows: int
    effective_windows: float
    coverage: float
    coverage_low: float
    coverage_high: float
    status: CalibrationStatusKey
    pit_histogram: list[int] = Field(default_factory=list)
    mean_pit: float
    brier_loss: float
    brier_beat_cdi: float
    log_score: float


class OriginForecastDTO(BaseModel):
    origin: date
    realized: float
    forecasts: dict[str, dict[str, float]] = Field(default_factory=dict)


class CalibrationDTO(BaseModel):
    """The latest (or a given) calibration; `run_id` is None when none was ever run."""

    run_id: int | None = None
    status: SimulationStatus | None = None
    finished_at: datetime | None = None
    error: str | None = None
    horizon_months: int = 12
    windows: int = 0
    effective_windows: float = 0.0
    first_origin: date | None = None
    last_origin: date | None = None
    classes: list[str] = Field(default_factory=list)
    targets: dict[str, float] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    generators: list[GeneratorCalibrationDTO] = Field(default_factory=list)
    origins: list[OriginForecastDTO] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # A newer calibration still queued or running.
    pending_run_id: int | None = None


class CandidateFitDTO(BaseModel):
    months: int
    alpha_annual: float
    alpha_post_annual: float
    alpha_post_sd_annual: float
    beta: float
    beta_post: float
    beta_post_sd: float
    shrinkage: float
    residual_vol_annual: float


class CandidateEffectDTO(BaseModel):
    ticker: str
    share_in_class: float
    weight: float
    delta_final_wealth: float
    p_improve: float
    p_improve_low: float
    p_improve_high: float
    delta_goal_probability: float | None = None
    delta_cvar_12m: float
    delta_drawdown: float
    delta_diversification: float
    delta_income_yield: float
    top_k_share: float = 0.0
    rank: int = 0


class CandidateResultDTO(BaseModel):
    ticker: str
    name: str
    arca_class: str
    asset_type: str
    source: str
    eligible: bool | None = None
    valuation_verdict: str | None = None
    dividend_yield: float | None = None
    suspicious: bool = False
    zone: str = "NO_DATA"
    fit: CandidateFitDTO
    effect: CandidateEffectDTO


class CandidateBaseDTO(BaseModel):
    final_net_wealth_p50: float
    cvar_12m: float
    drawdown_median: float
    diversification: float
    goal_probability: float | None = None


class ExcludedCandidateDTO(BaseModel):
    ticker: str
    reason: str


class CandidatesDTO(BaseModel):
    """Candidates to investigate, best first; never a purchase order."""

    run_id: int
    status: SimulationStatus
    horizon_months: int = 0
    paths: int = 0
    base: CandidateBaseDTO | None = None
    candidates: list[CandidateResultDTO] = Field(default_factory=list)
    excluded: list[ExcludedCandidateDTO] = Field(default_factory=list)
    tau_annual: dict[str, float] = Field(default_factory=dict)
    tested: int = 0
    evaluated: int = 0
    weight_mode: str = "NEXT_CONTRIBUTION"
    rupture_loss: float = 0.55
    sample_start: date | None = None
    sample_end: date | None = None
    calibration_run: int | None = None
    warnings: list[str] = Field(default_factory=list)
