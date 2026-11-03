"""SQLAlchemy repository of the saved views (Phase 48.R9).

It takes and returns pure domain entities and never commits
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.views.entities import SavedView, ViewScope
from domain.views.repositories import AbstractSavedViewRepository
from infra.data.models.views import SavedViewModel


def _view(m: SavedViewModel) -> SavedView:
    return SavedView(
        id=m.id,
        scope=ViewScope(m.scope),
        name=m.name,
        filters=dict(m.filters or {}),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class SqlAlchemySavedViewRepository(AbstractSavedViewRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_scope(self, scope: ViewScope) -> list[SavedView]:
        stmt = (
            select(SavedViewModel)
            .where(SavedViewModel.scope == scope.value)
            .order_by(SavedViewModel.name)
        )
        return [_view(m) for m in self.session.scalars(stmt)]

    def find(self, scope: ViewScope, name: str) -> SavedView | None:
        stmt = select(SavedViewModel).where(
            SavedViewModel.scope == scope.value, SavedViewModel.name == name
        )
        model = self.session.scalars(stmt).first()
        return _view(model) if model else None

    def save(self, view: SavedView) -> SavedView:
        model = self.session.get(SavedViewModel, view.id) if view.id else None
        if model is None:
            model = SavedViewModel(scope=view.scope.value, created_at=view.created_at)
            self.session.add(model)
        model.name = view.name
        model.filters = dict(view.filters)
        model.updated_at = view.updated_at
        self.session.flush()
        return _view(model)

    def delete(self, view_id: int) -> bool:
        model = self.session.get(SavedViewModel, view_id)
        if model is None:
            return False
        self.session.delete(model)
        self.session.flush()
        return True
