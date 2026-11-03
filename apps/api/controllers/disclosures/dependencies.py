"""FastAPI dependency providers of the CVM disclosures (Phase 28)."""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from domain.disclosures.services.use_cases import DisclosureHandler
from domain.shared.unit_of_work import UoWFactory


def get_disclosure_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> DisclosureHandler:
    """Provide the DisclosureHandler instance."""
    return DisclosureHandler(uow_factory=uow_factory)
