"""Use cases of Planejar (Phase 48.R8): goals with their progress and the future income."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from core.errors import NotFoundError, ValidationError
from domain.planning.goals import Goal, GoalKind, GoalProgress, progress_of
from domain.planning.income_forecast import DeclaredIncome, IncomeForecast, forecast_income
from domain.portfolio.services.income import summarize
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.unit_of_work import AbstractUnitOfWork, UoWFactory

MAX_GOALS = 50
FORECAST_MONTHS = (12, 24, 36)


def _validate(goal: Goal, today: date) -> None:
    if not goal.name.strip():
        raise ValidationError("The goal needs a name", code="EMPTY_GOAL_NAME")
    if goal.target_brl <= 0:
        raise ValidationError("The target must be positive", code="INVALID_TARGET")
    if goal.target_date <= today:
        raise ValidationError("The target date must be in the future", code="INVALID_TARGET_DATE")
    if goal.monthly_contribution_brl < 0:
        raise ValidationError(
            "The monthly contribution cannot be negative", code="INVALID_CONTRIBUTION"
        )
    if not (Decimal("-0.5") < goal.annual_return < Decimal("1")):
        raise ValidationError(
            "The assumed return must be between -50% and 100% a year", code="INVALID_RETURN"
        )
    if goal.kind == GoalKind.PASSIVE_INCOME and not (
        Decimal("0") < goal.income_yield < Decimal("1")
    ):
        raise ValidationError(
            "The income yield must be between 0% and 100% a year", code="INVALID_YIELD"
        )


def current_position(uow: AbstractUnitOfWork, today: date) -> tuple[float, float]:
    """(wealth from the latest snapshot, net passive income per month of the last 12 months)."""
    latest = uow.snapshots.latest_before(today + timedelta(days=1))
    wealth = float(latest.market_value) if latest else 0.0
    income = summarize(uow.assets.list_all(active_only=False), today, months=12)
    return wealth, income.last_12m_brl / 12.0


class GoalHandler:
    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def list(self, *, today: date | None = None) -> list[GoalProgress]:
        on = today or date.today()
        with self.uow_factory() as uow:
            goals = uow.goals.list_all()
            wealth, income = current_position(uow, on)
        return [progress_of(g, wealth=wealth, monthly_income=income, today=on) for g in goals]

    def _progress(self, goal_id: int, today: date) -> GoalProgress:
        return next(p for p in self.list(today=today) if p.goal.id == goal_id)

    def create(self, goal: Goal, *, today: date | None = None) -> GoalProgress:
        on = today or date.today()
        _validate(goal, on)
        with self.uow_factory() as uow:
            if len(uow.goals.list_all()) >= MAX_GOALS:
                raise ValidationError(f"At most {MAX_GOALS} goals", code="TOO_MANY_GOALS")
            saved = uow.goals.add(
                replace(goal, name=goal.name.strip(), created_at=datetime.now(UTC))
            )
            uow.commit()
        return self._progress(saved.id or 0, on)

    def update(self, goal_id: int, changes: dict, *, today: date | None = None) -> GoalProgress:
        on = today or date.today()
        with self.uow_factory() as uow:
            current = uow.goals.get(goal_id)
            if current is None:
                raise NotFoundError(f"Goal id={goal_id} not found")
            updated = replace(current, **{k: v for k, v in changes.items() if v is not None})
            if updated.is_active:
                _validate(updated, on)
            uow.goals.update(replace(updated, name=updated.name.strip()))
            uow.commit()
        return self._progress(goal_id, on)

    def delete(self, goal_id: int) -> None:
        with self.uow_factory() as uow:
            if not uow.goals.delete(goal_id):
                raise NotFoundError(f"Goal id={goal_id} not found")
            uow.commit()


class IncomeForecastHandler:
    """`GET /portfolio/income-forecast`: declared plus estimated income month by month."""

    def __init__(
        self, uow_factory: UoWFactory, portfolio_service: PortfolioApplicationService
    ) -> None:
        self.uow_factory = uow_factory
        self.portfolio_service = portfolio_service

    def forecast(self, *, months: int = 12, today: date | None = None) -> IncomeForecast:
        if months not in FORECAST_MONTHS:
            raise ValidationError(f"months must be one of {FORECAST_MONTHS}", code="INVALID_MONTHS")
        on = today or date.today()
        with self.uow_factory() as uow:
            agenda = self.portfolio_service.earnings_agenda(uow, as_of_date=on)
            assets = uow.assets.list_all(active_only=False)
        declared = [
            DeclaredIncome(
                asset_id=item.asset_id,
                ticker=item.ticker,
                payment_date=item.payment_date,
                net_brl=float((item.gross_amount or 0.0) - (item.withholding_tax or 0.0)),
            )
            for item in agenda.items
            if item.held and item.asset_id and item.payment_date and item.gross_amount
        ]
        return forecast_income(assets, declared, today=on, months=months)
