"""API configuration: re-exports the shared settings and derives domain configuration."""

from __future__ import annotations

from fincontrol_config import Settings, get_settings
from fincontrol_core.portfolio.consolidation import ProjectionAssumptions

AppSettings = Settings

__all__ = ["AppSettings", "Settings", "get_settings", "projection_assumptions"]


def projection_assumptions(settings: Settings) -> ProjectionAssumptions:
    """12-month projection premises configured through PROJECTION_* variables."""
    return ProjectionAssumptions(
        equity_capital_growth_rate=settings.projection_equity_growth_rate,
        fund_capital_growth_rate=settings.projection_fund_growth_rate,
        real_estate_default_yield_rate=settings.projection_real_estate_yield_rate,
        cash_cdi_multiplier=settings.projection_cash_cdi_multiplier,
        cash_income_tax_rate=settings.projection_cash_income_tax_rate,
    )
