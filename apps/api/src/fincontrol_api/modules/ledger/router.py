"""HTTP controllers (routers) of the ledger module; they only delegate to use cases.

Scope: transactions, earnings, corporate events and B3 statement imports.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fincontrol_core.domain.pagination import PaginationParams

from fincontrol_api.core.deps import pagination_query
from fincontrol_api.modules.ledger.dependencies import (
    get_earning_handler,
    get_event_handler,
    get_import_handler,
    get_transaction_handler,
)
from fincontrol_api.modules.ledger.schemas import (
    CorporateEventDTO,
    CorporateEventRequest,
    EarningCreateRequest,
    EarningResponseDTO,
    EarningUpdateRequest,
    ImportCommitDTO,
    ImportPreviewDTO,
    TransactionCreateRequest,
    TransactionResponseDTO,
    TransactionUpdateRequest,
)
from fincontrol_api.modules.ledger.use_cases.b3_import import ImportHandler
from fincontrol_api.modules.ledger.use_cases.corporate_events import CorporateEventHandler
from fincontrol_api.modules.ledger.use_cases.earnings import EarningHandler
from fincontrol_api.modules.ledger.use_cases.transactions import TransactionHandler
from fincontrol_api.modules.shared.schemas import PaginatedResponse

transactions_router = APIRouter(prefix="/transactions", tags=["Transactions"])


earnings_router = APIRouter(prefix="/earnings", tags=["Earnings"])


events_router = APIRouter(prefix="/corporate-events", tags=["Corporate Events"])


imports_router = APIRouter(prefix="/imports", tags=["Imports"])


@transactions_router.get("", response_model=PaginatedResponse[TransactionResponseDTO])
def list_transactions(
    params: PaginationParams = Depends(pagination_query),
    asset_id: int | None = Query(default=None),
    kind: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    account_id: int | None = Query(default=None),
    handler: TransactionHandler = Depends(get_transaction_handler),
) -> PaginatedResponse[TransactionResponseDTO]:
    return handler.list_paginated(
        params,
        asset_id=asset_id,
        kind=kind,
        date_from=date_from,
        date_to=date_to,
        account_id=account_id,
    )


@transactions_router.post(
    "", response_model=TransactionResponseDTO, status_code=status.HTTP_201_CREATED
)
def create_transaction(
    payload: TransactionCreateRequest,
    handler: TransactionHandler = Depends(get_transaction_handler),
) -> TransactionResponseDTO:
    return handler.create(payload)


@transactions_router.get("/{tx_id}", response_model=TransactionResponseDTO)
def get_transaction(
    tx_id: int,
    handler: TransactionHandler = Depends(get_transaction_handler),
) -> TransactionResponseDTO:
    return handler.get(tx_id)


@transactions_router.put("/{tx_id}", response_model=TransactionResponseDTO)
def update_transaction(
    tx_id: int,
    payload: TransactionUpdateRequest,
    handler: TransactionHandler = Depends(get_transaction_handler),
) -> TransactionResponseDTO:
    return handler.update(tx_id, payload)


@transactions_router.delete("/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    tx_id: int,
    handler: TransactionHandler = Depends(get_transaction_handler),
) -> Response:
    handler.delete(tx_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@earnings_router.get("", response_model=PaginatedResponse[EarningResponseDTO])
def list_earnings(
    params: PaginationParams = Depends(pagination_query),
    asset_id: int | None = Query(default=None),
    kind: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    account_id: int | None = Query(default=None),
    handler: EarningHandler = Depends(get_earning_handler),
) -> PaginatedResponse[EarningResponseDTO]:
    return handler.list_paginated(
        params,
        asset_id=asset_id,
        kind=kind,
        date_from=date_from,
        date_to=date_to,
        account_id=account_id,
    )


@earnings_router.post("", response_model=EarningResponseDTO, status_code=status.HTTP_201_CREATED)
def create_earning(
    payload: EarningCreateRequest,
    handler: EarningHandler = Depends(get_earning_handler),
) -> EarningResponseDTO:
    return handler.create(payload)


@earnings_router.get("/{earning_id}", response_model=EarningResponseDTO)
def get_earning(
    earning_id: int,
    handler: EarningHandler = Depends(get_earning_handler),
) -> EarningResponseDTO:
    return handler.get(earning_id)


@earnings_router.put("/{earning_id}", response_model=EarningResponseDTO)
def update_earning(
    earning_id: int,
    payload: EarningUpdateRequest,
    handler: EarningHandler = Depends(get_earning_handler),
) -> EarningResponseDTO:
    return handler.update(earning_id, payload)


@earnings_router.delete("/{earning_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_earning(
    earning_id: int,
    handler: EarningHandler = Depends(get_earning_handler),
) -> Response:
    handler.delete(earning_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@events_router.get("", response_model=list[CorporateEventDTO])
def list_corporate_events(
    asset_id: int | None = Query(default=None),
    handler: CorporateEventHandler = Depends(get_event_handler),
) -> list[CorporateEventDTO]:
    return handler.list_all(asset_id=asset_id)


@events_router.post("", response_model=CorporateEventDTO, status_code=status.HTTP_201_CREATED)
def create_corporate_event(
    payload: CorporateEventRequest,
    handler: CorporateEventHandler = Depends(get_event_handler),
) -> CorporateEventDTO:
    return handler.create(payload)


@events_router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_corporate_event(
    event_id: int,
    handler: CorporateEventHandler = Depends(get_event_handler),
) -> Response:
    handler.delete(event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@imports_router.post("/b3/preview", response_model=ImportPreviewDTO)
async def preview_b3_import(
    file: UploadFile = File(...),
    handler: ImportHandler = Depends(get_import_handler),
) -> ImportPreviewDTO:
    return handler.preview(file.filename or "", await file.read())


@imports_router.post("/b3/commit", response_model=ImportCommitDTO)
async def commit_b3_import(
    file: UploadFile = File(...),
    account_id: int | None = Form(default=None),
    create_tickers: str = Form(default="", description="Comma-separated unknown tickers to add"),
    handler: ImportHandler = Depends(get_import_handler),
) -> ImportCommitDTO:
    return handler.commit(
        file.filename or "",
        await file.read(),
        account_id=account_id,
        create_tickers=[t for t in create_tickers.split(",") if t.strip()],
    )
