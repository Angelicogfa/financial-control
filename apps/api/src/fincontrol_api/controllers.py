"""FastAPI Controllers / Routers (strictly delegating to Application Handlers)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from fincontrol_core.domain.pagination import PaginationParams

from fincontrol_api.dependencies import (
    get_asset_handler,
    get_earning_handler,
    get_market_data_handler,
    get_portfolio_handler,
    get_transaction_handler,
)
from fincontrol_api.handlers import (
    AssetHandler,
    EarningHandler,
    PortfolioHandler,
    TransactionHandler,
)
from fincontrol_api.handlers.market_handlers import MarketDataHandler
from fincontrol_api.schemas import (
    ArcaTargetItemDTO,
    ArcaTargetsUpdateRequest,
    AssetAnalysisResponseDTO,
    AssetCreateRequest,
    AssetResponseDTO,
    AssetUpdateRequest,
    CerradoUpdateRequest,
    ContributionPlanResponseDTO,
    ContributionSimulationRequest,
    EarningCreateRequest,
    EarningResponseDTO,
    EarningUpdateRequest,
    PaginatedResponse,
    PortfolioAnalyticsResponseDTO,
    PortfolioReportResponseDTO,
    SeriesStatusDTO,
    TransactionCreateRequest,
    TransactionResponseDTO,
    TransactionUpdateRequest,
)

health_router = APIRouter(tags=["Health"])
assets_router = APIRouter(prefix="/assets", tags=["Assets"])
transactions_router = APIRouter(prefix="/transactions", tags=["Transactions"])
earnings_router = APIRouter(prefix="/earnings", tags=["Earnings"])
portfolio_router = APIRouter(prefix="/portfolio", tags=["Portfolio & ARCA"])
settings_router = APIRouter(prefix="/settings", tags=["Settings"])
market_router = APIRouter(prefix="/market", tags=["Market Data"])


def pagination_query(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=200),
    sort_by: str = Query(default="id"),
    sort_order: str = Query(default="asc"),
    sort_dir: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> PaginationParams:
    """Parse standardized pagination, sorting, and search query parameters."""
    order = (sort_dir or sort_order).lower()
    return PaginationParams(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=order,
        search=search,
    )


# ---------------------------------------------------------------------------
# Health Controller
# ---------------------------------------------------------------------------
@health_router.get("/health")
def get_health() -> dict[str, str]:
    """Liveness and readiness check."""
    return {"status": "ok", "service": "fincontrol-api"}


# ---------------------------------------------------------------------------
# Assets Controller
# ---------------------------------------------------------------------------
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


@assets_router.post(
    "", response_model=AssetResponseDTO, status_code=status.HTTP_201_CREATED
)
def create_asset(
    payload: AssetCreateRequest,
    handler: AssetHandler = Depends(get_asset_handler),
) -> AssetResponseDTO:
    return handler.create(payload)


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


@assets_router.put("/{asset_id}/cerrado", response_model=AssetResponseDTO)
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


# ---------------------------------------------------------------------------
# Transactions Controller
# ---------------------------------------------------------------------------
@transactions_router.get("", response_model=PaginatedResponse[TransactionResponseDTO])
def list_transactions(
    params: PaginationParams = Depends(pagination_query),
    asset_id: int | None = Query(default=None),
    kind: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    handler: TransactionHandler = Depends(get_transaction_handler),
) -> PaginatedResponse[TransactionResponseDTO]:
    return handler.list_paginated(
        params,
        asset_id=asset_id,
        kind=kind,
        date_from=date_from,
        date_to=date_to,
    )


@transactions_router.post(
    "", response_model=TransactionResponseDTO, status_code=status.HTTP_201_CREATED
)
def create_transaction(
    payload: TransactionCreateRequest,
    handler: TransactionHandler = Depends(get_transaction_handler),
) -> TransactionResponseDTO:
    return handler.create(payload)


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


# ---------------------------------------------------------------------------
# Earnings (Proventos) Controller
# ---------------------------------------------------------------------------
@earnings_router.get("", response_model=PaginatedResponse[EarningResponseDTO])
def list_earnings(
    params: PaginationParams = Depends(pagination_query),
    asset_id: int | None = Query(default=None),
    kind: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    handler: EarningHandler = Depends(get_earning_handler),
) -> PaginatedResponse[EarningResponseDTO]:
    return handler.list_paginated(
        params,
        asset_id=asset_id,
        kind=kind,
        date_from=date_from,
        date_to=date_to,
    )


@earnings_router.post(
    "", response_model=EarningResponseDTO, status_code=status.HTTP_201_CREATED
)
def create_earning(
    payload: EarningCreateRequest,
    handler: EarningHandler = Depends(get_earning_handler),
) -> EarningResponseDTO:
    return handler.create(payload)


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


# ---------------------------------------------------------------------------
# Portfolio, Consolidation, Contribution & Analytics Controller
# ---------------------------------------------------------------------------
@portfolio_router.get("", response_model=PortfolioReportResponseDTO)
def get_portfolio(
    as_of_date: date | None = Query(default=None),
    date_from: date | None = Query(default=None),
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> PortfolioReportResponseDTO:
    return handler.get_portfolio_report(as_of_date=as_of_date, date_from=date_from)


@portfolio_router.get("/consolidated", response_model=PortfolioReportResponseDTO)
def get_consolidated_portfolio(
    as_of_date: date | None = Query(default=None),
    date_from: date | None = Query(default=None),
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> PortfolioReportResponseDTO:
    return handler.get_portfolio_report(as_of_date=as_of_date, date_from=date_from)


@portfolio_router.post("/contribution", response_model=ContributionPlanResponseDTO)
def simulate_contribution(
    payload: ContributionSimulationRequest,
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> ContributionPlanResponseDTO:
    return handler.simulate_contribution(payload)


@portfolio_router.get("/analytics", response_model=PortfolioAnalyticsResponseDTO)
def get_portfolio_analytics(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> PortfolioAnalyticsResponseDTO:
    return handler.get_analytics(date_from=date_from, date_to=date_to)


# ---------------------------------------------------------------------------
# ARCA Target Settings Controller
# ---------------------------------------------------------------------------
@settings_router.get("/arca-targets", response_model=list[ArcaTargetItemDTO])
def get_arca_targets(
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> list[ArcaTargetItemDTO]:
    return handler.get_arca_targets()


@settings_router.put("/arca-targets", response_model=list[ArcaTargetItemDTO])
def update_arca_targets(
    payload: ArcaTargetsUpdateRequest,
    handler: PortfolioHandler = Depends(get_portfolio_handler),
) -> list[ArcaTargetItemDTO]:
    return handler.update_arca_targets(payload)


# ---------------------------------------------------------------------------
# Market Data Diagnostics Controller
# ---------------------------------------------------------------------------
@market_router.get("/series-status", response_model=list[SeriesStatusDTO])
def get_series_status(
    handler: MarketDataHandler = Depends(get_market_data_handler),
) -> list[SeriesStatusDTO]:
    return handler.series_status()
