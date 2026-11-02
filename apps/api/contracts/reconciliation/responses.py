"""Response schemas of the position check against the B3 statement (Phase 48.R5)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from domain.reconciliation.entities import LineResolution, LineStatus


class ReconciliationLineDTO(BaseModel):
    id: int | None = None
    product: str
    ticker: str | None = None
    asset_id: int | None = None
    account_id: int | None = None
    institution: str | None = None
    b3_quantity: float
    ledger_quantity: float
    difference: float = Field(description="Statement minus ledger")
    status: LineStatus
    note: str = ""
    resolution: LineResolution = LineResolution.OPEN
    resolution_note: str | None = None
    resolved_at: datetime | None = None


class ReconciliationCountsDTO(BaseModel):
    match: int
    divergent: int
    only_b3: int
    only_ledger: int
    not_compared: int
    open_issues: int


class ReconciliationDTO(BaseModel):
    """A check of the Posição statement against the ledger; `id` is null in the preview."""

    id: int | None = None
    reference_date: date
    file_name: str
    created_at: datetime | None = None
    counts: ReconciliationCountsDTO
    lines: list[ReconciliationLineDTO]


class ReconciliationSummaryDTO(BaseModel):
    id: int
    reference_date: date
    file_name: str
    created_at: datetime | None = None
    counts: ReconciliationCountsDTO
