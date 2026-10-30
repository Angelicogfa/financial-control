"""HTTP controllers (routers) of the recommendation; they only delegate to use cases."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from controllers.recommendation.dependencies import get_recommendation_handler
from controllers.recommendation.responses import LensBoardDTO
from domain.recommendation.services import RecommendationHandler

recommendation_router = APIRouter(prefix="/recommendation", tags=["Recommendation"])


@recommendation_router.get("/lenses", response_model=LensBoardDTO)
def get_lenses(
    arca_class: str | None = Query(default=None),
    source: Literal["PORTFOLIO", "WATCHLIST", "CATALOG"] | None = Query(default=None),
    ticker: str | None = Query(default=None, max_length=16),
    eligible: bool | None = Query(default=None),
    handler: RecommendationHandler = Depends(get_recommendation_handler),
) -> LensBoardDTO:
    """The lenses (45.1) and gates (45.2) of each asset of the universe, from the weekly run."""
    return handler.lenses(arca_class=arca_class, source=source, ticker=ticker, eligible=eligible)
