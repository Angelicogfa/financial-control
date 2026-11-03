"""Pydantic request DTOs of the CVM disclosures (Phase 28)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MarkReadRequest(BaseModel):
    """Mark documents as read: by id, or every document in scope with `all`."""

    ids: list[int] = Field(default_factory=list, max_length=500)
    all: bool = False
    # With `all`: only the documents of this asset (default: every followed company).
    asset_id: int | None = None
