"""Pydantic response DTOs for the agentic configuration module.

Scope: personal MCP agent API keys and scoped tool grants.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AgentKeyDTO(BaseModel):
    """Metadata of an agent API key (never includes the secret key value)."""

    id: int
    name: str
    prefix: str
    user_id: str
    contexts: list[str]
    operations: list[str]
    expires_at: datetime
    last_used_at: datetime | None = None
    created_at: datetime | None = None
    revision: int = 1


class AgentKeyCreatedDTO(AgentKeyDTO):
    """Returned only once upon creation; carries the cleartext `fck_...` secret."""

    key: str


class GrantableOperationDTO(BaseModel):
    """An operation exposed as an MCP tool that can be granted to an agent key."""

    name: str
    kind: Literal["query", "command"]
    description: str
    grantable: bool = True


class GrantableContextDTO(BaseModel):
    """A functional module/context grouping grantable MCP operations."""

    name: str
    label: str
    grantable: bool = True
    operations: list[GrantableOperationDTO]


class GrantOptionsDTO(BaseModel):
    """All contexts and operations available to be granted to a personal agent key."""

    contexts: list[GrantableContextDTO]
