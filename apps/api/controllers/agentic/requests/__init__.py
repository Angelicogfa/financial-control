"""Pydantic request DTOs for the agentic configuration module.

Scope: personal MCP agent API keys and scoped tool grants.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

KeyExpiryDays = Literal[30, 90, 180, 365]


class AgentKeyCreateRequest(BaseModel):
    """Payload to generate a new personal MCP agent API key."""

    name: str = Field(..., min_length=1, max_length=128)
    contexts: list[str] = Field(default_factory=list)
    operations: list[str] = Field(default_factory=list)
    expires_in_days: KeyExpiryDays = 90


class AgentKeyUpdateRequest(BaseModel):
    """Payload to update the name and permission scope of an existing agent API key."""

    name: str = Field(..., min_length=1, max_length=128)
    contexts: list[str] = Field(default_factory=list)
    operations: list[str] = Field(default_factory=list)
    expected_revision: int = 1


class AgentKeyRenewRequest(BaseModel):
    """Payload to extend the validity of an existing agent API key from today."""

    expires_in_days: KeyExpiryDays = 90
