"""FastAPI dependency providers of the recommendation (Phase 45)."""

from __future__ import annotations

from fastapi import Depends

from composition import get_uow_factory
from controllers.shared.dependencies import UoWFactory
from domain.recommendation.services import RecommendationHandler


def get_recommendation_handler(
    uow_factory: UoWFactory = Depends(get_uow_factory),
) -> RecommendationHandler:
    """Provide the RecommendationHandler: it reads what the worker stored."""
    return RecommendationHandler(uow_factory=uow_factory)
