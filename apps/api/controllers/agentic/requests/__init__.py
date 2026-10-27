"""Pydantic request DTOs for the agentic configuration module.

Scope: personal MCP agent API keys and scoped tool grants.
"""

from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, Field


class KeyExpiryDays(IntEnum):
    DAYS_30 = 30
    DAYS_90 = 90
    DAYS_180 = 180
    DAYS_365 = 365


class AgentKeyCreateRequest(BaseModel):
    """Payload to generate a new personal MCP agent API key."""

    name: str = Field(..., min_length=1, max_length=128)
    contexts: list[str] = Field(default_factory=list)
    operations: list[str] = Field(default_factory=list)
    expires_in_days: KeyExpiryDays = KeyExpiryDays.DAYS_90


class AgentKeyUpdateRequest(BaseModel):
    """Payload to update the name and permission scope of an existing agent API key."""

    name: str = Field(..., min_length=1, max_length=128)
    contexts: list[str] = Field(default_factory=list)
    operations: list[str] = Field(default_factory=list)
    expected_revision: int = 1


class AgentKeyRenewRequest(BaseModel):
    """Payload to extend the validity of an existing agent API key from today."""

    expires_in_days: KeyExpiryDays = KeyExpiryDays.DAYS_90
