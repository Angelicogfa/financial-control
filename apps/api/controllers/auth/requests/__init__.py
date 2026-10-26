"""Pydantic request/response DTOs for the auth module.

Scope: single-user login session.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=1, max_length=256)


class CurrentUserDTO(BaseModel):
    username: str
    expires_at: datetime | None = None
