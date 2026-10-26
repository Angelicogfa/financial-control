"""SQLAlchemy repositories: alert dismissals.

They take and return pure domain entities and never commit
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.alerts.services.evaluator import AlertDismissal
from domain.shared.repositories import (
    AbstractAlertDismissalRepository,
)
from infra.data.models.alerts import AlertDismissalModel


class SqlAlchemyAlertDismissalRepository(AbstractAlertDismissalRepository):
    """SQLAlchemy implementation of AbstractAlertDismissalRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> list[AlertDismissal]:
        stmt = select(AlertDismissalModel).order_by(AlertDismissalModel.dismissed_at.desc())
        return [
            AlertDismissal(key=m.key, dismissed_at=m.dismissed_at, until=m.until)
            for m in self.session.scalars(stmt).all()
        ]

    def upsert(self, dismissal: AlertDismissal) -> AlertDismissal:
        model = self.session.get(AlertDismissalModel, dismissal.key)
        if model is None:
            model = AlertDismissalModel(key=dismissal.key)
            self.session.add(model)
        model.dismissed_at = dismissal.dismissed_at
        model.until = dismissal.until
        self.session.flush()
        return dismissal

    def delete(self, key: str) -> bool:
        model = self.session.get(AlertDismissalModel, key)
        if model is None:
            return False
        self.session.delete(model)
        self.session.flush()
        return True
