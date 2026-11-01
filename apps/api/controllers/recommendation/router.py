"""HTTP controllers (routers) of the recommendation; they only delegate to use cases."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from controllers.recommendation.dependencies import get_recommendation_handler
from controllers.recommendation.responses import (
    BacktestDTO,
    ContributionComparisonDTO,
    LensBoardDTO,
    LensWeightsDTO,
    MatrixBoardDTO,
    RecommendationRunDTO,
    RowComparisonDTO,
)
from domain.recommendation.services import RecommendationHandler

recommendation_router = APIRouter(prefix="/recommendation", tags=["Recommendation"])


@recommendation_router.get("/lenses", response_model=LensBoardDTO)
def get_lenses(
    arca_class: str | None = Query(default=None),
    source: Literal["PORTFOLIO", "WATCHLIST", "CATALOG"] | None = Query(default=None),
    ticker: str | None = Query(default=None, max_length=16),
    eligible: bool | None = Query(default=None),
    as_of: date | None = Query(default=None),
    handler: RecommendationHandler = Depends(get_recommendation_handler),
) -> LensBoardDTO:
    """The lenses (45.1) and gates (45.2) of each asset of the universe, from the weekly run."""
    return handler.lenses(
        arca_class=arca_class, source=source, ticker=ticker, eligible=eligible, as_of=as_of
    )


@recommendation_router.get("/matrix", response_model=MatrixBoardDTO)
def get_matrix(
    arca_class: str | None = Query(default=None),
    as_of: date | None = Query(default=None),
    handler: RecommendationHandler = Depends(get_recommendation_handler),
) -> MatrixBoardDTO:
    """The AHP decision matrix of each ARCA class (Phase 45.3), of the latest run or `as_of`."""
    return handler.matrix(arca_class=arca_class, as_of=as_of)


@recommendation_router.get("/runs", response_model=list[RecommendationRunDTO])
def get_runs(
    limit: int = Query(default=52, ge=1, le=520),
    handler: RecommendationHandler = Depends(get_recommendation_handler),
) -> list[RecommendationRunDTO]:
    """The history of the weekly runs (Phase 45.5), newest first."""
    return handler.runs(limit)


@recommendation_router.get("/compare", response_model=RowComparisonDTO)
def get_compare(
    a: str = Query(..., min_length=1, max_length=16),
    b: str = Query(..., min_length=1, max_length=16),
    handler: RecommendationHandler = Depends(get_recommendation_handler),
) -> RowComparisonDTO:
    """'A and not B': two assets of the same class, lens by lens."""
    return handler.compare(a, b)


@recommendation_router.get("/contribution", response_model=ContributionComparisonDTO)
def get_contribution(
    amount_brl: float = Query(..., gt=0),
    handler: RecommendationHandler = Depends(get_recommendation_handler),
) -> ContributionComparisonDTO:
    """The contribution the recommendation would make, next to the current one (nothing saved)."""
    return handler.contribution(amount_brl)


@recommendation_router.get("/backtest", response_model=BacktestDTO)
def get_backtest(
    handler: RecommendationHandler = Depends(get_recommendation_handler),
) -> BacktestDTO:
    """The hierarchy tested in the past and the scoreboard of its runs (Phase 45.6)."""
    return handler.backtest()


@recommendation_router.get("/weights", response_model=LensWeightsDTO)
def get_weights(
    handler: RecommendationHandler = Depends(get_recommendation_handler),
) -> LensWeightsDTO:
    """The lens weights validated by the data (Phase 45.7) and whether they are used."""
    return handler.weights()
