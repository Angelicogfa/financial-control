"""FastAPI dependency providers for the accounts module.

Scope: brokers, banks and exchanges that hold the assets.
"""

from __future__ import annotations

from fastapi import Depends

from fincontrol_api.composition import get_uow_factory
from fincontrol_api.core.deps import UoWFactory
from fincontrol_api.modules.accounts.use_cases import AccountHandler


def get_account_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> AccountHandler:
    """Provide the AccountHandler instance."""
    return AccountHandler(uow_factory=uow_factory)
