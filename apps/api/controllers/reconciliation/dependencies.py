"""FastAPI dependency providers for the position check (Phase 48.R5)."""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from domain.reconciliation.services import ReconciliationHandler
from domain.shared.unit_of_work import UoWFactory


def get_reconciliation_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> ReconciliationHandler:
    """Provide the ReconciliationHandler instance."""
    return ReconciliationHandler(uow_factory=uow_factory)
