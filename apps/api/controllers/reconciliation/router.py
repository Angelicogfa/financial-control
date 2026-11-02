"""HTTP controllers of the position check against the B3 Posição statement (Phase 48.R5).

Preview compares without saving; commit keeps the check. Neither writes to the ledger.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from contracts.reconciliation.requests import LineResolutionRequest
from contracts.reconciliation.responses import (
    ReconciliationDTO,
    ReconciliationLineDTO,
    ReconciliationSummaryDTO,
)
from contracts.reconciliation.serializers import to_line_dto, to_reconciliation_dto, to_summary_dto
from controllers.reconciliation.dependencies import get_reconciliation_handler
from domain.reconciliation.services import ReconciliationHandler

reconciliation_router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])

_DATE_HELP = "Data-base of the statement; taken from the B3 file name when omitted"


@reconciliation_router.post("/b3/preview", response_model=ReconciliationDTO)
async def preview_reconciliation(
    file: UploadFile = File(...),
    reference_date: date | None = Form(default=None, description=_DATE_HELP),
    handler: ReconciliationHandler = Depends(get_reconciliation_handler),
) -> ReconciliationDTO:
    return to_reconciliation_dto(
        handler.preview(file.filename or "", await file.read(), reference_date)
    )


@reconciliation_router.post("/b3/commit", response_model=ReconciliationDTO)
async def commit_reconciliation(
    file: UploadFile = File(...),
    reference_date: date | None = Form(default=None, description=_DATE_HELP),
    handler: ReconciliationHandler = Depends(get_reconciliation_handler),
) -> ReconciliationDTO:
    return to_reconciliation_dto(
        handler.commit(file.filename or "", await file.read(), reference_date)
    )


@reconciliation_router.get("", response_model=list[ReconciliationSummaryDTO])
def list_reconciliations(
    limit: int = Query(default=20, ge=1, le=100),
    handler: ReconciliationHandler = Depends(get_reconciliation_handler),
) -> list[ReconciliationSummaryDTO]:
    return [to_summary_dto(r) for r in handler.list_recent(limit)]


@reconciliation_router.get("/{reconciliation_id}", response_model=ReconciliationDTO)
def get_reconciliation(
    reconciliation_id: int,
    handler: ReconciliationHandler = Depends(get_reconciliation_handler),
) -> ReconciliationDTO:
    return to_reconciliation_dto(handler.get(reconciliation_id))


@reconciliation_router.put(
    "/{reconciliation_id}/lines/{line_id}", response_model=ReconciliationLineDTO
)
def resolve_reconciliation_line(
    reconciliation_id: int,
    line_id: int,
    payload: LineResolutionRequest,
    handler: ReconciliationHandler = Depends(get_reconciliation_handler),
) -> ReconciliationLineDTO:
    return to_line_dto(
        handler.resolve(reconciliation_id, line_id, payload.resolution, payload.note)
    )
