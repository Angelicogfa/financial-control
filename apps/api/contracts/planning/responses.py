"""Response schemas of Planejar: goals and future income (Phase 48.R8)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from domain.planning.goals import GoalKind, GoalStatus


class GoalDTO(BaseModel):
    id: int
    kind: GoalKind
    name: str
    target_brl: float
    target_date: date
    monthly_contribution_brl: float
    annual_return: float
    income_yield: float
    is_active: bool
    created_at: datetime | None = None
    months_left: int
    current_brl: float = Field(description="Wealth now, or the passive income per month now")
    target_wealth_brl: float = Field(description="The wealth the goal needs")
    current_wealth_brl: float
    progress: float = Field(description="Current over target, from 0 to 1")
    projected_wealth_brl: float = Field(
        description="At the target date with the planned contribution"
    )
    required_monthly_brl: float = Field(description="Monthly contribution that reaches the goal")
    status: GoalStatus


class ForecastMonthDTO(BaseModel):
    month: str = Field(description="YYYY-MM")
    declared_brl: float = Field(description="Already announced, net")
    estimated_brl: float = Field(description="From the last 12 months, at today's quantity")
    total_brl: float


class AssetIncomeForecastDTO(BaseModel):
    asset_id: int
    ticker: str
    next_12m_brl: float


class IncomeForecastDTO(BaseModel):
    """Passive income of the portfolio as it is now, month by month (Phase 48.R8)."""

    as_of: date
    months: list[ForecastMonthDTO]
    next_12m_brl: float
    declared_brl: float
    assets: list[AssetIncomeForecastDTO]
