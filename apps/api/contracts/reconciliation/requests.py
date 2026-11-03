"""Request schemas of the position check (Phase 48.R5)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from domain.reconciliation.entities import LineResolution


class LineResolutionRequest(BaseModel):
    resolution: LineResolution
    note: str | None = Field(default=None, max_length=500)
