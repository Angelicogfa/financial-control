"""Request schemas of Planejar: goals (Phase 48.R8)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from domain.planning.goals import DEFAULT_ANNUAL_RETURN, DEFAULT_INCOME_YIELD, GoalKind


class GoalCreateRequest(BaseModel):
    kind: GoalKind
    name: str = Field(..., min_length=1, max_length=120)
    target_brl: Decimal = Field(..., gt=0, description="Wealth, or the passive income per month")
    target_date: date
    monthly_contribution_brl: Decimal = Field(default=Decimal("0"), ge=0)
    annual_return: Decimal = Field(default=DEFAULT_ANNUAL_RETURN, description="Fraction a year")
    income_yield: Decimal = Field(
        default=DEFAULT_INCOME_YIELD, description="Fraction a year that the wealth pays as income"
    )


class GoalUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_brl: Decimal | None = Field(default=None, gt=0)
    target_date: date | None = None
    monthly_contribution_brl: Decimal | None = Field(default=None, ge=0)
    annual_return: Decimal | None = None
    income_yield: Decimal | None = None
    is_active: bool | None = None
