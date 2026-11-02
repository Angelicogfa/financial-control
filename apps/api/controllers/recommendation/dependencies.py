"""FastAPI dependency providers of the recommendation (Phase 45)."""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from controllers.portfolio.dependencies import get_portfolio_service
from domain.portfolio.services.service import PortfolioApplicationService
from domain.recommendation.services import RecommendationHandler
from domain.shared.unit_of_work import UoWFactory


def get_recommendation_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
    portfolio_service: PortfolioApplicationService = Depends(get_portfolio_service),
) -> RecommendationHandler:
    """Provide the RecommendationHandler: it reads what the worker stored."""
    return RecommendationHandler(uow_factory=uow_factory, portfolio_service=portfolio_service)
