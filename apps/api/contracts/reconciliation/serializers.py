"""Entity -> response schema of the position check (Phase 48.R5)."""

from __future__ import annotations

from contracts.reconciliation.responses import (
    ReconciliationCountsDTO,
    ReconciliationDTO,
    ReconciliationLineDTO,
    ReconciliationSummaryDTO,
)
from domain.reconciliation.entities import LineStatus, PositionReconciliation, ReconciliationLine


def to_line_dto(line: ReconciliationLine) -> ReconciliationLineDTO:
    return ReconciliationLineDTO(
        id=line.id,
        product=line.product,
        ticker=line.ticker,
        asset_id=line.asset_id,
        account_id=line.account_id,
        institution=line.institution,
        b3_quantity=float(line.b3_quantity),
        ledger_quantity=float(line.ledger_quantity),
        difference=float(line.difference),
        status=line.status,
        note=line.note,
        resolution=line.resolution,
        resolution_note=line.resolution_note,
        resolved_at=line.resolved_at,
    )


def to_counts_dto(r: PositionReconciliation) -> ReconciliationCountsDTO:
    return ReconciliationCountsDTO(
        match=r.count(LineStatus.MATCH),
        divergent=r.count(LineStatus.DIVERGENT),
        only_b3=r.count(LineStatus.ONLY_B3),
        only_ledger=r.count(LineStatus.ONLY_LEDGER),
        not_compared=r.count(LineStatus.NOT_COMPARED),
        open_issues=r.open_issues,
    )


def to_reconciliation_dto(r: PositionReconciliation) -> ReconciliationDTO:
    return ReconciliationDTO(
        id=r.id,
        reference_date=r.reference_date,
        file_name=r.file_name,
        created_at=r.created_at,
        counts=to_counts_dto(r),
        lines=[to_line_dto(line) for line in r.lines],
    )


def to_summary_dto(r: PositionReconciliation) -> ReconciliationSummaryDTO:
    return ReconciliationSummaryDTO(
        id=r.id or 0,
        reference_date=r.reference_date,
        file_name=r.file_name,
        created_at=r.created_at,
        counts=to_counts_dto(r),
    )
