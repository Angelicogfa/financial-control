"""FastAPI dependency providers for the accounts module.

Scope: brokers, banks and exchanges that hold the assets.
"""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from domain.accounts.services.use_cases import AccountHandler
from domain.shared.unit_of_work import UoWFactory


def get_account_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> AccountHandler:
    """Provide the AccountHandler instance."""
    return AccountHandler(uow_factory=uow_factory)
