"""FastAPI dependency providers for the policy module.

Scope: versioned investment policy and ARCA targets.
"""

from __future__ import annotations

from fastapi import Depends

from fincontrol_api.composition import get_uow_factory
from fincontrol_api.core.deps import UoWFactory
from fincontrol_api.modules.policy.use_cases import PolicyHandler


def get_policy_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> PolicyHandler:
    """Provide the PolicyHandler instance."""
    return PolicyHandler(uow_factory=uow_factory)
