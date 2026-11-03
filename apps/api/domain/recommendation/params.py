"""Parameters of the construction of the weights (Phase 45.4), kept free of imports so the
investment policy can hold them without a cycle."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConstructionParams:
    risk_aversion: float = 0.2  # lambda: expected return a year given up per unit of volatility
    k_min: int = 3
    k_max: int = 12
    sector_cap: float = 0.25
    group_cap: float = 0.25
    max_per_sector: int = 2
    sector_margin_sd: float = 0.5
    asset_cap: float = 1.0  # of the class; the portfolio's limit seen from the class
