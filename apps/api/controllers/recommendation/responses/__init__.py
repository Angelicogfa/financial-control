"""Pydantic response DTOs of the recommendation (Phase 45)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class LensDTO(BaseModel):
    """One lens of an asset: higher `normalized` is always better (Phase 45.1)."""

    lens: Literal[
        "CERRADO",
        "QUALITY",
        "VALUATION",
        "IMPROVEMENT",
        "MOMENTUM",
        "INCOME",
        "RISK",
        "PROJECTION",
    ]
    label: str
    value: float | None = None  # CERRADO: 0-10; the others: z against the sector (±3)
    normalized: float | None = None  # [0, 1]; None without data
    confidence: float
    note: str
    flags: list[str] = Field(default_factory=list)  # NOT_ANALYZED, PARTIAL, STALE, CERRADO_OFF


class GateDTO(BaseModel):
    """One gate of an asset (Phase 45.2): only FAIL takes the asset out."""

    gate: Literal["LEDGER", "LIQUIDITY", "HISTORY", "RUIN", "DATA"]
    label: str
    status: Literal["PASS", "FAIL", "WARN", "NOT_APPLICABLE"]
    reason: str


class AssetLensesDTO(BaseModel):
    ticker: str
    source: Literal["PORTFOLIO", "WATCHLIST", "CATALOG"]
    arca_class: str | None = None
    sector: str = ""
    signal_ticker: str | None = None  # the share class the company's signals are measured on
    lenses: list[LensDTO] = Field(default_factory=list)
    eligible: bool | None = None  # passed every gate; None when the gates were not computed
    gates: list[GateDTO] = Field(default_factory=list)


class LensBoardDTO(BaseModel):
    """The lenses of the universe (portfolio, watchlist and liquid catalog stocks)."""

    status: Literal["OK", "NOT_COMPUTED"]
    as_of: date | None = None
    assets: list[AssetLensesDTO] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)  # assets per source
    eligible: int = 0  # assets that passed every gate
