"""Repository port of the saved views (Phase 48.R9)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.views.entities import SavedView, ViewScope


class AbstractSavedViewRepository(ABC):
    @abstractmethod
    def list_scope(self, scope: ViewScope) -> list[SavedView]: ...

    @abstractmethod
    def find(self, scope: ViewScope, name: str) -> SavedView | None: ...

    @abstractmethod
    def save(self, view: SavedView) -> SavedView:
        """Insert, or replace the filters of the view with the same id."""

    @abstractmethod
    def delete(self, view_id: int) -> bool: ...
