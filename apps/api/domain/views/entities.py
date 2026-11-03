"""Saved views (Phase 48.R9): a name for the filters of a screen, kept across sessions and
devices instead of only in the browser session."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ViewScope(StrEnum):
    """The screen whose filters a view keeps."""

    SCREENER = "SCREENER"  # Explorar › Screener
    LEDGER = "LEDGER"  # Lançamentos
    PORTFOLIO = "PORTFOLIO"  # Carteira › Posições


@dataclass(frozen=True)
class SavedView:
    scope: ViewScope
    name: str
    filters: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: int | None = None
