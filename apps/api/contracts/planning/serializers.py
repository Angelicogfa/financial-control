"""Read model -> response schema of Planejar (Phase 48.R8)."""

from __future__ import annotations

from contracts.planning.responses import (
    AssetIncomeForecastDTO,
    ForecastMonthDTO,
    GoalDTO,
    IncomeForecastDTO,
)
from domain.planning.goals import GoalProgress
from domain.planning.income_forecast import IncomeForecast


def to_goal_dto(p: GoalProgress) -> GoalDTO:
    g = p.goal
    return GoalDTO(
        id=g.id or 0,
        kind=g.kind,
        name=g.name,
        target_brl=float(g.target_brl),
        target_date=g.target_date,
        monthly_contribution_brl=float(g.monthly_contribution_brl),
        annual_return=float(g.annual_return),
        income_yield=float(g.income_yield),
        is_active=g.is_active,
        created_at=g.created_at,
        months_left=p.months_left,
        current_brl=p.current_brl,
        target_wealth_brl=p.target_wealth_brl,
        current_wealth_brl=p.current_wealth_brl,
        progress=p.progress,
        projected_wealth_brl=p.projected_wealth_brl,
        required_monthly_brl=p.required_monthly_brl,
        status=p.status,
    )


def to_income_forecast_dto(f: IncomeForecast) -> IncomeForecastDTO:
    return IncomeForecastDTO(
        as_of=f.as_of,
        months=[
            ForecastMonthDTO(
                month=m.month,
                declared_brl=m.declared_brl,
                estimated_brl=m.estimated_brl,
                total_brl=m.total_brl,
            )
            for m in f.months
        ],
        next_12m_brl=f.next_12m_brl,
        declared_brl=f.declared_brl,
        assets=[
            AssetIncomeForecastDTO(
                asset_id=a.asset_id, ticker=a.ticker, next_12m_brl=a.next_12m_brl
            )
            for a in f.assets
        ],
    )
