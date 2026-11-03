"""Use cases of the saved views (Phase 48.R9): saving under a name that already exists in
the screen replaces its filters, so "Salvar visão" works the same for new and old names."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from core.errors import NotFoundError, ValidationError
from domain.shared.unit_of_work import UoWFactory
from domain.views.entities import SavedView, ViewScope

MAX_VIEWS_PER_SCOPE = 30
MAX_FILTERS_CHARS = 4_000
MAX_NAME = 80


def clean_name(name: str, filters: dict[str, Any]) -> str:
    """The name with single spaces; refuses an empty or long name and oversized filters."""
    clean = " ".join(name.split())
    if not clean:
        raise ValidationError("The view needs a name", code="EMPTY_VIEW_NAME")
    if len(clean) > MAX_NAME:
        raise ValidationError(f"At most {MAX_NAME} characters", code="VIEW_NAME_TOO_LONG")
    if len(json.dumps(filters, ensure_ascii=False)) > MAX_FILTERS_CHARS:
        raise ValidationError("The filters are too large", code="VIEW_FILTERS_TOO_LARGE")
    return clean


class SavedViewHandler:
    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def list(self, scope: ViewScope) -> list[SavedView]:
        with self.uow_factory() as uow:
            return uow.saved_views.list_scope(scope)

    def save(self, scope: ViewScope, name: str, filters: dict[str, Any]) -> SavedView:
        clean = clean_name(name, filters)
        now = datetime.now(UTC)
        with self.uow_factory() as uow:
            current = uow.saved_views.find(scope, clean)
            if current is None:
                if len(uow.saved_views.list_scope(scope)) >= MAX_VIEWS_PER_SCOPE:
                    raise ValidationError(
                        f"At most {MAX_VIEWS_PER_SCOPE} views per screen", code="TOO_MANY_VIEWS"
                    )
                view = SavedView(scope, clean, filters, created_at=now, updated_at=now)
            else:
                view = replace(current, filters=filters, updated_at=now)
            saved = uow.saved_views.save(view)
            uow.commit()
        return saved

    def delete(self, view_id: int) -> None:
        with self.uow_factory() as uow:
            if not uow.saved_views.delete(view_id):
                raise NotFoundError(f"Saved view id={view_id} not found")
            uow.commit()
