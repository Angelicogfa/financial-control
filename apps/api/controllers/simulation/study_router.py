"""HTTP controllers of the simulation studies (Phase 41); they only delegate to the handler."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from controllers.simulation.dependencies import get_study_handler
from controllers.simulation.requests import StudyRequest, StudyVariationRequest
from controllers.simulation.responses import (
    StudyComparisonDTO,
    StudyDTO,
    StudySummaryDTO,
    StudyVersionDTO,
)
from domain.simulation.services.studies import StudyHandler

study_router = APIRouter(prefix="/studies", tags=["Simulation studies"])


@study_router.get("", response_model=list[StudySummaryDTO])
def list_studies(
    limit: int = Query(default=50, ge=1, le=200),
    handler: StudyHandler = Depends(get_study_handler),
) -> list[StudySummaryDTO]:
    """Latest version of each study, newest first, with its headline and goal chance."""
    return handler.list(limit)


@study_router.post("", response_model=StudyDTO, status_code=status.HTTP_202_ACCEPTED)
def create_study(
    payload: StudyRequest,
    handler: StudyHandler = Depends(get_study_handler),
) -> StudyDTO:
    """Create a study and queue its chapters (the worker runs them in order)."""
    return handler.create(payload)


@study_router.get("/compare", response_model=StudyComparisonDTO)
def compare_studies(
    a: int = Query(...),
    b: int = Query(...),
    handler: StudyHandler = Depends(get_study_handler),
) -> StudyComparisonDTO:
    """Two studies side by side, chapter by chapter, with the premises that differ."""
    return handler.compare(a, b)


@study_router.get("/{study_id}", response_model=StudyDTO)
def get_study(
    study_id: int,
    handler: StudyHandler = Depends(get_study_handler),
) -> StudyDTO:
    return handler.get(study_id)


@study_router.get("/{study_id}/versions", response_model=list[StudyVersionDTO])
def list_versions(
    study_id: int,
    handler: StudyHandler = Depends(get_study_handler),
) -> list[StudyVersionDTO]:
    """Every version of the study, oldest first (the goal chance over time)."""
    return handler.versions(study_id)


@study_router.post(
    "/{study_id}/refresh", response_model=StudyDTO, status_code=status.HTTP_202_ACCEPTED
)
def refresh_study(
    study_id: int,
    handler: StudyHandler = Depends(get_study_handler),
) -> StudyDTO:
    """The same premises with today's data: a new version; the previous one is kept."""
    return handler.refresh(study_id)


@study_router.post(
    "/{study_id}/variations", response_model=StudyDTO, status_code=status.HTTP_202_ACCEPTED
)
def create_variation(
    study_id: int,
    payload: StudyVariationRequest,
    handler: StudyHandler = Depends(get_study_handler),
) -> StudyDTO:
    """A copy of the study with some premises changed, ready to compare."""
    return handler.variation(study_id, payload)


@study_router.delete("/{study_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_study(
    study_id: int,
    handler: StudyHandler = Depends(get_study_handler),
) -> Response:
    """Delete a study and its runs for good (logical deletion, no restore)."""
    handler.delete(study_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
