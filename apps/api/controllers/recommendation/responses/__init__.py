"""Pydantic response DTOs of the recommendation (Phase 45)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class LensDTO(BaseModel):
    """One lens of an asset: higher `normalized` is always better (Phase 45.1)."""

    lens: Literal[
        "CERRADO",
        "QUALITY",
        "VALUATION",
        "IMPROVEMENT",
        "MOMENTUM",
        "INCOME",
        "RISK",
        "PROJECTION",
    ]
    label: str
    value: float | None = None  # CERRADO: 0-10; the others: z against the sector (±3)
    normalized: float | None = None  # [0, 1]; None without data
    confidence: float
    note: str
    flags: list[str] = Field(default_factory=list)  # NOT_ANALYZED, PARTIAL, STALE, CERRADO_OFF


class GateDTO(BaseModel):
    """One gate of an asset (Phase 45.2): only FAIL takes the asset out."""

    gate: Literal["LEDGER", "LIQUIDITY", "HISTORY", "RUIN", "DATA"]
    label: str
    status: Literal["PASS", "FAIL", "WARN", "NOT_APPLICABLE"]
    reason: str


class AssetLensesDTO(BaseModel):
    ticker: str
    source: Literal["PORTFOLIO", "WATCHLIST", "CATALOG"]
    arca_class: str | None = None
    sector: str = ""
    signal_ticker: str | None = None  # the share class the company's signals are measured on
    lenses: list[LensDTO] = Field(default_factory=list)
    eligible: bool | None = None  # passed every gate; None when the gates were not computed
    gates: list[GateDTO] = Field(default_factory=list)


class LensBoardDTO(BaseModel):
    """The lenses of the universe (portfolio, watchlist and liquid catalog stocks)."""

    status: Literal["OK", "NOT_COMPUTED"]
    as_of: date | None = None
    assets: list[AssetLensesDTO] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)  # assets per source
    eligible: int = 0  # assets that passed every gate


LensKey = Literal[
    "CERRADO",
    "QUALITY",
    "VALUATION",
    "IMPROVEMENT",
    "MOMENTUM",
    "INCOME",
    "RISK",
    "PROJECTION",
]


class LensWeightDTO(BaseModel):
    lens: LensKey
    label: str
    weight: float  # AHP weight of the class's objective
    gaussian_weight: float  # Gaussian AHP reference (not used)


class MatrixCellDTO(BaseModel):
    lens: LensKey
    value: float  # [0, 1], pulled toward 0.5 by the lens's confidence
    weight: float
    contribution: float


class MatrixRowDTO(BaseModel):
    ticker: str
    source: Literal["PORTFOLIO", "WATCHLIST", "CATALOG"]
    sector: str = ""
    rank: int
    score: float  # [0, 1]
    expected: float  # a year over the class, on the declared scale
    expected_low: float
    expected_high: float
    confidence: float
    cells: list[MatrixCellDTO] = Field(default_factory=list)
    gaussian_score: float
    gaussian_rank: int
    flags: list[str] = Field(default_factory=list)  # the Cerrado's highlights


class ExcludedAssetDTO(BaseModel):
    ticker: str
    source: Literal["PORTFOLIO", "WATCHLIST", "CATALOG"]
    reasons: list[str] = Field(default_factory=list)


class CurvePointDTO(BaseModel):
    k: int
    added: str
    expected: float  # weighted expected return over the class, a year
    risk: float  # annual volatility of the set
    utility: float  # expected - lambda x risk


class SelectedAssetDTO(BaseModel):
    ticker: str
    sector: str
    group: str  # correlation group (named by its first member)
    weight: float  # target inside the class, before the pull toward the current weights
    score: float
    expected: float
    confidence: float
    reason: str


class SkippedAssetDTO(BaseModel):
    ticker: str
    reason: str


class ConstructionDTO(BaseModel):
    """The weights of the class (Phase 45.4): dynamic K, caps per sector and group."""

    k: int
    stop_reason: str
    confidence: float
    selected: list[SelectedAssetDTO] = Field(default_factory=list)
    skipped: list[SkippedAssetDTO] = Field(default_factory=list)
    curve: list[CurvePointDTO] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ClassMatrixDTO(BaseModel):
    """The decision matrix of one ARCA class (Phase 45.3): eligible assets ranked by the AHP."""

    arca_class: str
    objective: Literal["GROWTH", "DIVIDENDS", "MIXED"]
    objective_label: str
    consistency_ratio: float
    scale_annual: float  # expected return over the class of a score of 1 (declared premise)
    weights: list[LensWeightDTO] = Field(default_factory=list)
    rows: list[MatrixRowDTO] = Field(default_factory=list)
    excluded: list[ExcludedAssetDTO] = Field(default_factory=list)
    construction: ConstructionDTO | None = None
    weights_source: Literal["AHP", "VALIDATED"] = "AHP"  # VALIDATED: by the data (Phase 45.7)


class MatrixBoardDTO(BaseModel):
    status: Literal["OK", "NOT_COMPUTED"]
    as_of: date | None = None
    classes: list[ClassMatrixDTO] = Field(default_factory=list)


class LensDifferenceDTO(BaseModel):
    lens: LensKey
    label: str
    a: float
    b: float
    weight: float
    difference: float  # what this lens added to A's lead over B (negative: it favoured B)


class RowComparisonDTO(BaseModel):
    """'A and not B' (Phase 45.3): the two rows of the decision matrix, lens by lens."""

    status: Literal["OK", "NOT_COMPUTED", "NOT_COMPARABLE"]
    reason: str = ""
    a: MatrixRowDTO | None = None
    b: MatrixRowDTO | None = None
    differences: list[LensDifferenceDTO] = Field(default_factory=list)


class OrderLineDTO(BaseModel):
    ticker: str
    amount: float
    quantity: float
    unit_price: float | None = None
    target_weight: float | None = None  # inside the class
    current_weight: float | None = None
    new: bool = False  # not in the portfolio today
    reason: str = ""


class ClassComparisonDTO(BaseModel):
    """One class of the contribution: the policy's old strategy (`current_orders`) next to the
    contribution, which follows the recommendation (`recommended_orders`, Phase 45.6b)."""

    arca_class: str
    budget: float  # the class's share of the contribution (current ARCA rule, unchanged)
    covered: bool  # the recommendation has a construction for this class
    note: str = ""
    confidence: float | None = None  # how much the targets moved away from the current weights
    current_orders: list[OrderLineDTO] = Field(default_factory=list)
    recommended_orders: list[OrderLineDTO] = Field(default_factory=list)
    recommended_leftover: float = 0.0


class ContributionComparisonDTO(BaseModel):
    """The contribution, which follows the recommendation since Phase 45.6b, next to what the
    policy's old strategy would buy. Nothing is saved."""

    status: Literal["OK", "NOT_COMPUTED"]
    as_of: date | None = None  # the weekly run of the lenses
    amount: float
    classes: list[ClassComparisonDTO] = Field(default_factory=list)


class RecommendationRunDTO(BaseModel):
    """One weekly run of the recommendation (Phase 45.5)."""

    as_of: date
    policy_version: int | None = None
    signal_month: date | None = None
    assets: int
    eligible: int
    selected: dict[str, list[str]] = Field(default_factory=dict)  # class -> chosen tickers


class BacktestYearDTO(BaseModel):
    year: int
    months: int
    strategy: float  # compounded return over the class in the year
    equal: float


class ScoreLineDTO(BaseModel):
    horizon: int  # months after the run
    runs: int
    vs_equal: float  # mean return difference over the horizon
    beat_equal: float
    beat_equal_low: float
    beat_equal_high: float
    vs_cerrado: float | None = None
    beat_cerrado: float | None = None
    cerrado_runs: int = 0


class BacktestDTO(BaseModel):
    """The hierarchy tested in the past and the scoreboard of its runs (Phase 45.6)."""

    status: Literal["OK", "INSUFFICIENT", "NOT_COMPUTED"]
    as_of: date | None = None
    passed: bool = False
    reason: str = ""
    first_month: str | None = None
    last_month: str | None = None
    months: int = 0
    rebalances: int = 0
    average_k: float = 0.0
    strategy_annual: float = 0.0
    equal_annual: float = 0.0
    difference_annual: float = 0.0
    hit_rate: float = 0.0
    probability: float = 0.5
    years: list[BacktestYearDTO] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    scoreboard: list[ScoreLineDTO] = Field(default_factory=list)


class LensWeightLineDTO(BaseModel):
    lens: LensKey
    label: str
    declared: float  # AHP weight
    estimate_annual_per_z: float  # what the data say: extra return a year per unit of z
    sign_probability: float
    data: float  # the data's weight (0 when the sign is not clear or it hurts)
    candidate: float  # half declared, half data
    used: float


class LensWeightsDTO(BaseModel):
    """The lens weights validated by the data (Phase 45.7): used only if they pass the gate."""

    status: Literal["OK", "NOT_COMPUTED"]
    as_of: date | None = None
    objective: str | None = None
    passed: bool = False
    reason: str = ""
    origins: int = 0
    oos_months: int = 0
    improvement_annual: float = 0.0
    probability: float = 0.5
    lines: list[LensWeightLineDTO] = Field(default_factory=list)


class LiveSummaryDTO(BaseModel):
    start: date
    end: date
    final_value: float
    contributed: float
    gain: float
    irr: float | None = None  # annual money-weighted return of the flow
    twr: float
    annual_twr: float
    volatility: float
    max_drawdown: float
    fees: float
    taxes: float


class LiveRankDTO(BaseModel):
    portfolios: int
    beaten: int
    share: float
    low: float
    high: float


class LiveLineDTO(BaseModel):
    key: str
    label: str
    started: date
    retroactive: bool
    whole: LiveSummaryDTO
    yours: LiveSummaryDTO  # your portfolio over the same period
    difference: float
    prospective: LiveSummaryDTO | None = None
    yours_prospective: LiveSummaryDTO | None = None


class LiveRandomDTO(BaseModel):
    portfolios: int
    rank: LiveRankDTO | None = None
    rank_prospective: LiveRankDTO | None = None
    irr_low: float | None = None
    irr_mid: float | None = None
    irr_high: float | None = None


class LiveCurvePointDTO(BaseModel):
    day: date
    yours: float
    values: dict[str, float] = Field(default_factory=dict)
    random_low: float | None = None
    random_high: float | None = None


class LiveBoardDTO(BaseModel):
    """The live scoreboard (Phase 45.8a): the same ARCA flow under each strategy."""

    status: Literal["OK", "NOT_COMPUTED"]
    as_of: date | None = None
    prospective_since: date | None = None
    prospective_months: int = 0
    verdict_ready: bool = False
    yours: LiveSummaryDTO | None = None
    lines: list[LiveLineDTO] = Field(default_factory=list)
    randoms: LiveRandomDTO | None = None
    curve: list[LiveCurvePointDTO] = Field(default_factory=list)
