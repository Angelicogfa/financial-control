"""Goals of the investor and how far they are (Phase 48.R8, Planejar › Metas). Pure.

A goal is a wealth to reach, or a passive income per month (which needs the wealth that pays
it at the assumed yield), by a date, with a planned monthly contribution. Progress starts
from the latest portfolio snapshot and the income of the last 12 months; the projection
compounds the current wealth and the contributions at the assumed return, monthly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

DEFAULT_ANNUAL_RETURN = Decimal("0.06")  # real return assumed when the goal gives none
DEFAULT_INCOME_YIELD = Decimal("0.06")  # yearly yield that turns wealth into passive income


class GoalKind(StrEnum):
    WEALTH = "WEALTH"
    PASSIVE_INCOME = "PASSIVE_INCOME"  # target is the monthly income


class GoalStatus(StrEnum):
    REACHED = "REACHED"
    ON_TRACK = "ON_TRACK"
    OFF_TRACK = "OFF_TRACK"
    MISSED = "MISSED"  # the date passed without reaching it


@dataclass(frozen=True)
class Goal:
    kind: GoalKind
    name: str
    target_brl: Decimal
    target_date: date
    monthly_contribution_brl: Decimal = Decimal("0")
    annual_return: Decimal = DEFAULT_ANNUAL_RETURN
    income_yield: Decimal = DEFAULT_INCOME_YIELD
    is_active: bool = True
    created_at: datetime | None = None
    id: int | None = None


@dataclass(frozen=True)
class GoalProgress:
    goal: Goal
    months_left: int
    current_brl: float  # wealth now (income per month now, for passive income)
    target_wealth_brl: float  # the wealth the goal needs
    current_wealth_brl: float
    progress: float  # current over target, capped at 1
    projected_wealth_brl: float  # at the target date with the planned contribution
    required_monthly_brl: float  # contribution that reaches the target exactly
    status: GoalStatus


def months_between(start: date, end: date) -> int:
    """Whole months from `start` to `end` (0 when `end` is not after `start`)."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def monthly_rate(annual: Decimal) -> float:
    return (1.0 + float(annual)) ** (1.0 / 12.0) - 1.0


def future_value(present: float, contribution: float, rate: float, months: int) -> float:
    growth = (1.0 + rate) ** months
    if rate == 0:
        return present + contribution * months
    return present * growth + contribution * (growth - 1.0) / rate


def required_contribution(present: float, target: float, rate: float, months: int) -> float:
    """Monthly contribution so that `present` plus the contributions reach `target`."""
    if months <= 0:
        return max(target - present, 0.0)
    growth = (1.0 + rate) ** months
    missing = target - present * growth
    if missing <= 0:
        return 0.0
    return missing / months if rate == 0 else missing * rate / (growth - 1.0)


def target_wealth(goal: Goal) -> float:
    if goal.kind == GoalKind.WEALTH:
        return float(goal.target_brl)
    yearly = float(goal.income_yield)
    return float(goal.target_brl) * 12.0 / yearly if yearly > 0 else float("inf")


def progress_of(goal: Goal, *, wealth: float, monthly_income: float, today: date) -> GoalProgress:
    need = target_wealth(goal)
    months = months_between(today, goal.target_date)
    rate = monthly_rate(goal.annual_return)
    projected = future_value(wealth, float(goal.monthly_contribution_brl), rate, months)
    current = wealth if goal.kind == GoalKind.WEALTH else monthly_income
    target = float(goal.target_brl)
    reached = current >= target
    if reached:
        status = GoalStatus.REACHED
    elif goal.target_date <= today:
        status = GoalStatus.MISSED
    else:
        status = GoalStatus.ON_TRACK if projected >= need else GoalStatus.OFF_TRACK
    return GoalProgress(
        goal=goal,
        months_left=months,
        current_brl=round(current, 2),
        target_wealth_brl=round(need, 2),
        current_wealth_brl=round(wealth, 2),
        progress=round(min(current / target, 1.0), 4) if target > 0 else 1.0,
        projected_wealth_brl=round(projected, 2),
        required_monthly_brl=round(
            0.0 if reached else required_contribution(wealth, need, rate, months), 2
        ),
        status=status,
    )
