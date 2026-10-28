"""FastAPI dependency providers for the simulation module (Phase 33)."""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from controllers.shared.dependencies import UoWFactory
from core.settings import AppSettings, get_settings
from domain.simulation.services.use_cases import SimulationHandler


def get_simulation_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    settings: AppSettings = Depends(get_settings),
) -> SimulationHandler:
    """Provide the SimulationHandler instance."""
    return SimulationHandler(uow_factory=uow_factory, catalog_top=settings.simulation_catalog_top)
