"""HTTP controllers (routers) of the assets module; they only delegate to use cases.

Scope: asset registry, checklist and fundamentalist analysis.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from controllers.assets.dependencies import (
    get_asset_handler,
    get_forecast_handler,
    get_statements_handler,
)
from controllers.assets.requests import AssetCreateRequest, AssetUpdateRequest, CerradoUpdateRequest
from controllers.assets.responses import (
    ArcaSuggestionDTO,
    AssetAnalysisResponseDTO,
    AssetForecastDTO,
    AssetPriceHistoryDTO,
    AssetResponseDTO,
    PriceRange,
)
from controllers.disclosures.responses import AssetStatementsDTO
from controllers.shared.dependencies import pagination_query
from controllers.shared.responses import PaginatedResponse
from core.helpers.pagination import PaginationParams
from domain.assets.services.use_cases import AssetHandler
from domain.disclosures.services.statements_view import StatementsHandler
from domain.forecast.services import ForecastHandler
from domain.shared.enums import AssetType

assets_router = APIRouter(prefix="/assets", tags=["Assets"])


@assets_router.get("", response_model=PaginatedResponse[AssetResponseDTO])
def list_assets(
    params: PaginationParams = Depends(pagination_query),
    arca_class: str | None = Query(default=None),
    asset_type: str | None = Query(default=None),
    use_cerrado: bool | None = Query(default=None),
    active_only: bool = Query(default=True),
    handler: AssetHandler = Depends(get_asset_handler),
) -> PaginatedResponse[AssetResponseDTO]:
    return handler.list_paginated(
        params,
        arca_class=arca_class,
        asset_type=asset_type,
        use_cerrado=use_cerrado,
        active_only=active_only,
    )


@assets_router.post("", response_model=AssetResponseDTO, status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreateRequest,
    handler: AssetHandler = Depends(get_asset_handler),
) -> AssetResponseDTO:
    return handler.create(payload)


@assets_router.get("/classification", response_model=ArcaSuggestionDTO)
def suggest_asset_classification(
    ticker: str = Query(..., min_length=1, max_length=32),
    asset_type: AssetType = Query(...),
    handler: AssetHandler = Depends(get_asset_handler),
) -> ArcaSuggestionDTO:
    """ARCA class suggested by what the instrument is exposed to (ETF catalog) or its type."""
    return handler.suggest_classification(ticker, asset_type)


@assets_router.get("/{asset_id}", response_model=AssetResponseDTO)
def get_asset(
    asset_id: int,
    handler: AssetHandler = Depends(get_asset_handler),
) -> AssetResponseDTO:
    return handler.get_by_id(asset_id)


@assets_router.put("/{asset_id}", response_model=AssetResponseDTO)
def update_asset(
    asset_id: int,
    payload: AssetUpdateRequest,
    handler: AssetHandler = Depends(get_asset_handler),
) -> AssetResponseDTO:
    return handler.update(asset_id, payload)


@assets_router.put("/{asset_id}/checklist", response_model=AssetResponseDTO)
@assets_router.put("/{asset_id}/cerrado", response_model=AssetResponseDTO, deprecated=True)
def update_asset_cerrado(
    asset_id: int,
    payload: CerradoUpdateRequest,
    handler: AssetHandler = Depends(get_asset_handler),
) -> AssetResponseDTO:
    return handler.update_cerrado(asset_id, payload)


@assets_router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: int,
    hard: bool = Query(default=False),
    handler: AssetHandler = Depends(get_asset_handler),
) -> Response:
    handler.delete(asset_id, hard=hard)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@assets_router.get("/{asset_id}/analysis", response_model=AssetAnalysisResponseDTO)
def get_asset_analysis(
    asset_id: int,
    handler: AssetHandler = Depends(get_asset_handler),
) -> AssetAnalysisResponseDTO:
    return handler.get_analysis(asset_id)


@assets_router.get("/{asset_id}/forecast", response_model=AssetForecastDTO)
def get_asset_forecast(
    asset_id: int,
    handler: ForecastHandler = Depends(get_forecast_handler),
) -> AssetForecastDTO:
    """Probable price range at 3, 6, 12 and 24 months and the chances that matter (Phase 42)."""
    return handler.get(asset_id)


@assets_router.post("/{asset_id}/forecast", response_model=AssetForecastDTO)
def refresh_asset_forecast(
    asset_id: int,
    handler: ForecastHandler = Depends(get_forecast_handler),
) -> AssetForecastDTO:
    """Compute this asset's forecast now from the stored history (12 months on, with a warning)."""
    return handler.refresh(asset_id)


@assets_router.get("/{asset_id}/statements", response_model=AssetStatementsDTO)
def get_asset_statements(
    asset_id: int,
    handler: StatementsHandler = Depends(get_statements_handler),
) -> AssetStatementsDTO:
    """Statements delivered to the CVM, point in time, and today's indicators (Phase 42.2)."""
    return handler.get(asset_id)


@assets_router.get("/{asset_id}/prices", response_model=AssetPriceHistoryDTO)
def get_asset_prices(
    asset_id: int,
    range_period: PriceRange = Query(default="1y", alias="range"),
    handler: AssetHandler = Depends(get_asset_handler),
) -> AssetPriceHistoryDTO:
    return handler.get_prices(asset_id, range_period)
