"""Pydantic request/response DTOs for the accounts module.

Scope: brokers, banks and exchanges that hold the assets.
"""

from __future__ import annotations

from datetime import datetime

from fincontrol_core.domain.enums import (
    AccountKind,
)
from pydantic import BaseModel, Field


class AccountRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    institution: str | None = Field(default=None, max_length=120)
    kind: AccountKind = AccountKind.BROKER
    is_active: bool = True


class AccountDTO(AccountRequest):
    id: int
    created_at: datetime | None = None
