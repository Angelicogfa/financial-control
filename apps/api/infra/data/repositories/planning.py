"""SQLAlchemy repository of the goals (Phase 48.R8).

It takes and returns pure domain entities and never commits
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.planning.goals import Goal, GoalKind
from domain.planning.repositories import AbstractGoalRepository
from infra.data.models.planning import GoalModel


def _goal(m: GoalModel) -> Goal:
    return Goal(
        id=m.id,
        kind=GoalKind(m.kind),
        name=m.name,
        target_brl=m.target_brl,
        target_date=m.target_date,
        monthly_contribution_brl=m.monthly_contribution_brl,
        annual_return=m.annual_return,
        income_yield=m.income_yield,
        is_active=m.is_active,
        created_at=m.created_at,
    )


class SqlAlchemyGoalRepository(AbstractGoalRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> list[Goal]:
        stmt = select(GoalModel).order_by(GoalModel.target_date, GoalModel.id)
        return [_goal(m) for m in self.session.scalars(stmt)]

    def get(self, goal_id: int) -> Goal | None:
        model = self.session.get(GoalModel, goal_id)
        return _goal(model) if model else None

    def _write(self, model: GoalModel, goal: Goal) -> None:
        model.kind = goal.kind.value
        model.name = goal.name
        model.target_brl = goal.target_brl
        model.target_date = goal.target_date
        model.monthly_contribution_brl = goal.monthly_contribution_brl
        model.annual_return = goal.annual_return
        model.income_yield = goal.income_yield
        model.is_active = goal.is_active

    def add(self, goal: Goal) -> Goal:
        model = GoalModel(created_at=goal.created_at)
        self._write(model, goal)
        self.session.add(model)
        self.session.flush()
        return _goal(model)

    def update(self, goal: Goal) -> Goal:
        model = self.session.get(GoalModel, goal.id)
        if model is None:
            raise LookupError(f"goal {goal.id} not found")
        self._write(model, goal)
        self.session.flush()
        return _goal(model)

    def delete(self, goal_id: int) -> bool:
        model = self.session.get(GoalModel, goal_id)
        if model is None:
            return False
        self.session.delete(model)
        self.session.flush()
        return True
