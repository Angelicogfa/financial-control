"""FastAPI dependency providers for the instrument page and the global search."""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from domain.instruments.services import InstrumentHandler, SearchHandler
from domain.shared.unit_of_work import UoWFactory


def get_instrument_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> InstrumentHandler:
    """Provide the InstrumentHandler instance."""
    return InstrumentHandler(uow_factory=uow_factory)


def get_search_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> SearchHandler:
    """Provide the SearchHandler instance."""
    return SearchHandler(uow_factory=uow_factory)
