"""Keys of the recommendation's lenses and objectives (Phase 45).

Kept apart from the lens computations so the investment policy can hold the AHP matrices
without importing the asset services.
"""

from __future__ import annotations

CERRADO = "CERRADO"
QUALITY = "QUALITY"
VALUATION = "VALUATION"
IMPROVEMENT = "IMPROVEMENT"
MOMENTUM = "MOMENTUM"
INCOME = "INCOME"
RISK = "RISK"
PROJECTION = "PROJECTION"
LENSES = (CERRADO, QUALITY, VALUATION, IMPROVEMENT, MOMENTUM, INCOME, RISK, PROJECTION)

LENS_LABELS = {
    CERRADO: "Cerrado",
    QUALITY: "Qualidade",
    VALUATION: "Valuation",
    IMPROVEMENT: "Melhora",
    MOMENTUM: "Momentum",
    INCOME: "Renda",
    RISK: "Risco",
    PROJECTION: "Projeção",
}

# Objective of each ARCA class (design N0).
GROWTH = "GROWTH"
DIVIDENDS = "DIVIDENDS"
MIXED = "MIXED"
OBJECTIVES = (GROWTH, DIVIDENDS, MIXED)
OBJECTIVE_LABELS = {GROWTH: "Valorização", DIVIDENDS: "Dividendos", MIXED: "Misto"}
