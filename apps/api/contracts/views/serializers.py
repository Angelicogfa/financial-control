"""Entity -> response schema of the saved views (Phase 48.R9)."""

from __future__ import annotations

from contracts.views.responses import SavedViewDTO
from domain.views.entities import SavedView


def to_saved_view_dto(v: SavedView) -> SavedViewDTO:
    return SavedViewDTO(
        id=v.id or 0,
        scope=v.scope,
        name=v.name,
        filters=v.filters,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )
