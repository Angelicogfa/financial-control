"""Forward-looking premises used by 12-month projections (finding I-11)."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProjectionAssumptions:
    """Forward-looking assumptions for 12-month projections (finding I-11).

    Rates are annual fractions (ADR 0006). They are surfaced in every report so the user
    always sees which premises produced a projection.
    """

    equity_capital_growth_rate: float = 0.08
    fund_capital_growth_rate: float = 0.10
    real_estate_default_yield_rate: float = 0.085
    cash_cdi_multiplier: float = 1.0
    cash_income_tax_rate: float = 0.175

    def as_dict(self) -> dict[str, float]:
        return asdict(self)
