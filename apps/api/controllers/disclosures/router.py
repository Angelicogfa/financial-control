"""HTTP controllers (routers) of the CVM disclosures; they only delegate to use cases."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from controllers.disclosures.dependencies import get_disclosure_handler
from controllers.disclosures.requests import MarkReadRequest
from controllers.disclosures.responses import DisclosureFeedDTO, EventStudyDTO, MarkReadResultDTO
from domain.disclosures.services.use_cases import DisclosureHandler

disclosures_router = APIRouter(prefix="/disclosures", tags=["Disclosures"])


@disclosures_router.get("", response_model=DisclosureFeedDTO)
def get_feed(
    asset_id: int | None = Query(default=None),
    category: list[str] = Query(default_factory=list),
    unread: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    handler: DisclosureHandler = Depends(get_disclosure_handler),
) -> DisclosureFeedDTO:
    return handler.feed(asset_id=asset_id, categories=category, unread_only=unread, limit=limit)


@disclosures_router.get("/event-study", response_model=EventStudyDTO)
def get_event_study(
    handler: DisclosureHandler = Depends(get_disclosure_handler),
) -> EventStudyDTO:
    """What usually happens to the price after each kind of CVM event (Phase 42.4)."""
    return handler.event_study()


@disclosures_router.post("/read", response_model=MarkReadResultDTO)
def mark_read(
    req: MarkReadRequest,
    handler: DisclosureHandler = Depends(get_disclosure_handler),
) -> MarkReadResultDTO:
    return MarkReadResultDTO(updated=handler.mark_read(req))
