"""HTTP controllers of the instrument page and of the global search (Phase 48.R2).

`/instruments/{key}` opens any ticker or Tesouro symbol without registering it; `/search` finds
registered assets, the B3 catalog and the Tesouro catalog. Both only read the database.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from contracts.assets.responses import AssetPriceHistoryDTO, PriceRange
from contracts.instruments.responses import InstrumentViewDTO, SearchResultDTO
from contracts.instruments.serializers import (
    to_instrument_view_dto,
    to_price_history_dto,
    to_search_result_dto,
)
from controllers.instruments.dependencies import get_instrument_handler, get_search_handler
from domain.instruments.services import MAX_SEARCH_LIMIT, InstrumentHandler, SearchHandler

instruments_router = APIRouter(prefix="/instruments", tags=["Instruments"])
search_router = APIRouter(prefix="/search", tags=["Instruments"])


@instruments_router.get("/{key}", response_model=InstrumentViewDTO)
def get_instrument(
    key: str,
    handler: InstrumentHandler = Depends(get_instrument_handler),
) -> InstrumentViewDTO:
    return to_instrument_view_dto(handler.view(key))


@instruments_router.get("/{key}/prices", response_model=AssetPriceHistoryDTO)
def get_instrument_prices(
    key: str,
    range_period: PriceRange = Query(default="1y", alias="range"),
    handler: InstrumentHandler = Depends(get_instrument_handler),
) -> AssetPriceHistoryDTO:
    return to_price_history_dto(handler.prices(key, range_period))


@search_router.get("", response_model=SearchResultDTO)
def search_instruments(
    q: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(default=10, ge=1, le=MAX_SEARCH_LIMIT),
    handler: SearchHandler = Depends(get_search_handler),
) -> SearchResultDTO:
    return to_search_result_dto(handler.search(q, limit=limit))
