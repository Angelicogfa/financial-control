"""Response schemas of the saved views (Phase 48.R9)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from domain.views.entities import ViewScope


class SavedViewDTO(BaseModel):
    id: int
    scope: ViewScope
    name: str
    filters: dict[str, Any]
    created_at: datetime | None
    updated_at: datetime | None
