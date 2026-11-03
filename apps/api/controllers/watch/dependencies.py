"""FastAPI dependency providers for Acompanhar (Phase 48.R6)."""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from domain.shared.unit_of_work import UoWFactory
from domain.watch.services import AlertRuleHandler, AssetNoteHandler


def get_alert_rule_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> AlertRuleHandler:
    """Provide the AlertRuleHandler instance."""
    return AlertRuleHandler(uow_factory=uow_factory)


def get_asset_note_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> AssetNoteHandler:
    """Provide the AssetNoteHandler instance."""
    return AssetNoteHandler(uow_factory=uow_factory)
