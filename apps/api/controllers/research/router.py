"""HTTP controllers (routers) of the research module; they only delegate to use cases.

Scope: B3 catalog screener and watchlist.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status

from controllers.research.dependencies import (
    get_mining_handler,
    get_research_handler,
    get_statement_refresher,
)
from controllers.research.requests import WatchlistAddRequest, WatchlistClassifyRequest
from controllers.research.responses import (
    AssetComparisonDTO,
    MiningUniverseDTO,
    ScreenerResponseDTO,
    TreasurySearchResponseDTO,
    WatchlistItemDTO,
)
from domain.mining.services import MiningHandler
from domain.research.services.screener import ScreenerCriteria
from domain.research.services.service import StatementRefresher
from domain.research.services.use_cases import ResearchHandler
from domain.shared.enums import ArcaClass, AssetType, FixedIncomeIndexer

research_router = APIRouter(prefix="/research", tags=["Research"])


@research_router.get("/screener", response_model=ScreenerResponseDTO)
def run_screener(
    asset_type: list[AssetType] = Query(default=[]),
    arca_class: list[ArcaClass] = Query(default=[]),
    sector: list[str] = Query(default=[]),
    q: str | None = Query(default=None, max_length=60),
    min_volume_brl: float | None = Query(default=None, ge=0),
    min_market_cap: float | None = Query(default=None, ge=0),
    max_pe: float | None = Query(default=None, gt=0),
    max_pb: float | None = Query(default=None, gt=0),
    min_dy: float | None = Query(default=None, ge=0, description="Fraction: 0.06 = 6%"),
    min_roe: float | None = Query(default=None, description="Fraction: 0.15 = 15%"),
    below_band: bool = Query(default=False, description="Only ARCA classes below their band"),
    exclude_registered: bool = Query(default=False),
    limit: int = Query(default=30, ge=1, le=100, description="Page size"),
    page: int = Query(default=1, ge=1),
    handler: ResearchHandler = Depends(get_research_handler),
) -> ScreenerResponseDTO:
    criteria = ScreenerCriteria(
        asset_types=frozenset(asset_type),
        arca_classes=frozenset(arca_class),
        sectors=frozenset(sector),
        query=q,
        min_volume_brl=min_volume_brl,
        min_market_cap=min_market_cap,
        max_pe=max_pe,
        max_pb=max_pb,
        min_dy=min_dy,
        min_roe=min_roe,
        exclude_registered=exclude_registered,
        limit=limit,
        offset=(page - 1) * limit,
    )
    return handler.screener(criteria, below_band=below_band)


@research_router.get("/mining/universe", response_model=MiningUniverseDTO)
def get_mining_universe(
    handler: MiningHandler = Depends(get_mining_handler),
) -> MiningUniverseDTO:
    """The liquid stocks the Garimpo looks at and how far their history goes (Phase 43.1)."""
    return handler.universe()


@research_router.get("/sectors", response_model=list[str])
def list_sectors(handler: ResearchHandler = Depends(get_research_handler)) -> list[str]:
    return handler.sectors()


@research_router.get("/treasury", response_model=TreasurySearchResponseDTO)
def list_treasury_bonds(
    q: str | None = Query(default=None, max_length=60),
    indexer: FixedIncomeIndexer | None = Query(default=None),
    coupon_type: str | None = Query(default=None, pattern="^(zero|semestral)$"),
    handler: ResearchHandler = Depends(get_research_handler),
) -> TreasurySearchResponseDTO:
    return handler.treasury(query=q, indexer=indexer, coupon_type=coupon_type)


@research_router.get("/watchlist", response_model=list[WatchlistItemDTO])
def list_watchlist(
    handler: ResearchHandler = Depends(get_research_handler),
) -> list[WatchlistItemDTO]:
    return handler.watchlist()


@research_router.post(
    "/watchlist", response_model=WatchlistItemDTO, status_code=status.HTTP_201_CREATED
)
def add_to_watchlist(
    payload: WatchlistAddRequest,
    background: BackgroundTasks,
    handler: ResearchHandler = Depends(get_research_handler),
    statements: StatementRefresher = Depends(get_statement_refresher),
) -> WatchlistItemDTO:
    item = handler.add(payload)
    background.add_task(statements.refresh, [item.ticker])
    return item


@research_router.put("/watchlist/{asset_id}/classification", response_model=WatchlistItemDTO)
def classify_watchlist_item(
    asset_id: int,
    payload: WatchlistClassifyRequest,
    handler: ResearchHandler = Depends(get_research_handler),
) -> WatchlistItemDTO:
    return handler.classify(asset_id, payload)


@research_router.delete("/watchlist/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_watchlist(
    asset_id: int,
    handler: ResearchHandler = Depends(get_research_handler),
) -> Response:
    handler.remove(asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@research_router.get("/compare", response_model=AssetComparisonDTO)
def compare_assets(
    tickers: list[str] = Query(..., description="2 to 5 tickers (repeated or comma-separated)"),
    indicators: list[str] = Query(default=[], description="Indicator keys; all when empty"),
    handler: ResearchHandler = Depends(get_research_handler),
) -> AssetComparisonDTO:
    return handler.compare(tickers, indicators or None)
