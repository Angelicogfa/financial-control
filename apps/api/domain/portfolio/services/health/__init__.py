"""Portfolio health diagnosis in seven pillars (Phase 29, MARKET_ANALYSIS §7.3).

Every check returns ok / atenção / crítico (or "dados insuficientes" when its minimum window
is not met), the measured value, the limits of the versioned policy, an explanation and the
suggested action. A pillar takes the state of its worst check and the report lists the
pillars worst first, so a critical check is never diluted by an average.

The engine is pure: the application service loads positions, return series and statements
and hands them over as `HealthInputs`.
"""

from __future__ import annotations

from domain.portfolio.services.health.common import (
    issuer_of,
    worst,
)
from domain.portfolio.services.health.diagnosis import (
    ASSET_SERIES_CHECKS,
    PORTFOLIO_SERIES_CHECKS,
    diagnose,
)
from domain.portfolio.services.health.model import (
    DIVERSIFIED_TYPES,
    LOW_F_SCORE,
    MIN_CONSISTENCY_MONTHS,
    MIN_DRAWDOWN_OBSERVATIONS,
    PILLAR_TITLES,
    SOVEREIGN_TYPES,
    UNKNOWN_SECTOR,
    VARIABLE_INCOME_TYPES,
    Z_DISTRESS,
    BracketLot,
    ConcentrationBreakdown,
    CorrelatedPair,
    DiversificationDetail,
    HealthCheck,
    HealthInputs,
    HealthPillar,
    HealthReport,
    HealthStatus,
    HealthUnit,
    Holding,
    HoldingQuality,
    InstitutionExposure,
    LiquidityDetail,
    Maturity,
    PerformanceDetail,
    PillarResult,
    RiskDetail,
    RiskShare,
)

__all__ = [
    "ASSET_SERIES_CHECKS",
    "BracketLot",
    "ConcentrationBreakdown",
    "CorrelatedPair",
    "DIVERSIFIED_TYPES",
    "DiversificationDetail",
    "HealthCheck",
    "HealthInputs",
    "HealthPillar",
    "HealthReport",
    "HealthStatus",
    "HealthUnit",
    "Holding",
    "HoldingQuality",
    "InstitutionExposure",
    "LOW_F_SCORE",
    "LiquidityDetail",
    "MIN_CONSISTENCY_MONTHS",
    "MIN_DRAWDOWN_OBSERVATIONS",
    "Maturity",
    "PILLAR_TITLES",
    "PORTFOLIO_SERIES_CHECKS",
    "PerformanceDetail",
    "PillarResult",
    "RiskDetail",
    "RiskShare",
    "SOVEREIGN_TYPES",
    "UNKNOWN_SECTOR",
    "VARIABLE_INCOME_TYPES",
    "Z_DISTRESS",
    "diagnose",
    "issuer_of",
    "worst",
]
