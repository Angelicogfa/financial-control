"""FastAPI dependency providers for the policy module.

Scope: versioned investment policy and ARCA targets.
"""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from domain.policy.services.use_cases import PolicyHandler
from domain.shared.unit_of_work import UoWFactory


def get_policy_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> PolicyHandler:
    """Provide the PolicyHandler instance."""
    return PolicyHandler(uow_factory=uow_factory)
