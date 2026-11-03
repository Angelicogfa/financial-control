"""FastAPI dependency providers for the saved views (Phase 48.R9)."""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from domain.shared.unit_of_work import UoWFactory
from domain.views.services import SavedViewHandler


def get_saved_view_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> SavedViewHandler:
    """Provide the SavedViewHandler instance."""
    return SavedViewHandler(uow_factory=uow_factory)
