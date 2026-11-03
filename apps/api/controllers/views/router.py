"""HTTP controllers of the saved views (Phase 48.R9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from contracts.views.requests import SavedViewRequest
from contracts.views.responses import SavedViewDTO
from contracts.views.serializers import to_saved_view_dto
from controllers.views.dependencies import get_saved_view_handler
from domain.views.entities import ViewScope
from domain.views.services import SavedViewHandler

saved_views_router = APIRouter(prefix="/saved-views", tags=["Saved views"])


@saved_views_router.get("", response_model=list[SavedViewDTO])
def list_saved_views(
    scope: ViewScope = Query(...),
    handler: SavedViewHandler = Depends(get_saved_view_handler),
) -> list[SavedViewDTO]:
    return [to_saved_view_dto(v) for v in handler.list(scope)]


@saved_views_router.put("", response_model=SavedViewDTO)
def save_view(
    payload: SavedViewRequest, handler: SavedViewHandler = Depends(get_saved_view_handler)
) -> SavedViewDTO:
    """Save the filters under a name; an existing name in the same screen is replaced."""
    return to_saved_view_dto(handler.save(payload.scope, payload.name, payload.filters))


@saved_views_router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_view(
    view_id: int, handler: SavedViewHandler = Depends(get_saved_view_handler)
) -> Response:
    handler.delete(view_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
