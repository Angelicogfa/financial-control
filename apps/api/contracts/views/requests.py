"""Request schemas of the saved views (Phase 48.R9)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from domain.views.entities import ViewScope


class SavedViewRequest(BaseModel):
    scope: ViewScope
    name: str = Field(..., min_length=1, max_length=80)
    filters: dict[str, Any] = Field(default_factory=dict)
