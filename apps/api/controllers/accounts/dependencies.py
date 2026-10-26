"""FastAPI dependency providers for the accounts module.

Scope: brokers, banks and exchanges that hold the assets.
"""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from controllers.shared.dependencies import UoWFactory
from domain.accounts.services.use_cases import AccountHandler


def get_account_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> AccountHandler:
    """Provide the AccountHandler instance."""
    return AccountHandler(uow_factory=uow_factory)
