"""SQLAlchemy repository of the live scoreboard (Phase 45.8a).

It takes and returns pure domain entities and never commits
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.comparison.points import Point
from domain.comparison.repositories import AbstractComparisonRepository, ComparisonPortfolio
from infra.data.models.comparison import ComparisonPortfolioModel


def _entity(m: ComparisonPortfolioModel) -> ComparisonPortfolio:
    return ComparisonPortfolio(
        id=m.id,
        key=m.key,
        variant=m.variant,
        label=m.label,
        created_on=m.created_on,
        state=dict(m.state or {}),
        points=[Point.from_dict(p) for p in m.points or []],
    )


class SqlAlchemyComparisonRepository(AbstractComparisonRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> list[ComparisonPortfolio]:
        stmt = select(ComparisonPortfolioModel).order_by(
            ComparisonPortfolioModel.key, ComparisonPortfolioModel.variant
        )
        return [_entity(m) for m in self.session.scalars(stmt)]

    def get(self, key: str, variant: int = 0) -> ComparisonPortfolio | None:
        stmt = select(ComparisonPortfolioModel).where(
            ComparisonPortfolioModel.key == key, ComparisonPortfolioModel.variant == variant
        )
        model = self.session.scalars(stmt).first()
        return _entity(model) if model else None

    def save(self, portfolio: ComparisonPortfolio) -> None:
        stmt = select(ComparisonPortfolioModel).where(
            ComparisonPortfolioModel.key == portfolio.key,
            ComparisonPortfolioModel.variant == portfolio.variant,
        )
        model = self.session.scalars(stmt).first()
        if model is None:
            model = ComparisonPortfolioModel(key=portfolio.key, variant=portfolio.variant)
            self.session.add(model)
        model.label = portfolio.label
        model.created_on = portfolio.created_on
        model.state = dict(portfolio.state)
        model.points = [p.to_dict() for p in portfolio.points]
        self.session.flush()
        portfolio.id = model.id
