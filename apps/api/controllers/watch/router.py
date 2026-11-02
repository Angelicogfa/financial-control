"""HTTP controllers of Acompanhar: alert rules and thesis notes (Phase 48.R6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from contracts.watch.requests import (
    AlertRuleCreateRequest,
    AlertRuleUpdateRequest,
    AssetNoteRequest,
)
from contracts.watch.responses import AlertRuleDTO, AssetNoteDTO
from contracts.watch.serializers import to_note_dto, to_rule_dto
from controllers.watch.dependencies import get_alert_rule_handler, get_asset_note_handler
from domain.watch.services import AlertRuleHandler, AssetNoteHandler

alert_rules_router = APIRouter(prefix="/alert-rules", tags=["Watch"])
notes_router = APIRouter(tags=["Watch"])


@alert_rules_router.get("", response_model=list[AlertRuleDTO])
def list_alert_rules(
    handler: AlertRuleHandler = Depends(get_alert_rule_handler),
) -> list[AlertRuleDTO]:
    return [to_rule_dto(r) for r in handler.list()]


@alert_rules_router.post("", response_model=AlertRuleDTO, status_code=status.HTTP_201_CREATED)
def create_alert_rule(
    payload: AlertRuleCreateRequest,
    handler: AlertRuleHandler = Depends(get_alert_rule_handler),
) -> AlertRuleDTO:
    return to_rule_dto(
        handler.create(
            payload.ticker, payload.metric, payload.operator, payload.threshold, payload.note
        )
    )


@alert_rules_router.put("/{rule_id}", response_model=AlertRuleDTO)
def update_alert_rule(
    rule_id: int,
    payload: AlertRuleUpdateRequest,
    handler: AlertRuleHandler = Depends(get_alert_rule_handler),
) -> AlertRuleDTO:
    return to_rule_dto(
        handler.update(
            rule_id, threshold=payload.threshold, is_active=payload.is_active, note=payload.note
        )
    )


@alert_rules_router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert_rule(
    rule_id: int, handler: AlertRuleHandler = Depends(get_alert_rule_handler)
) -> Response:
    handler.delete(rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@notes_router.get("/notes", response_model=list[AssetNoteDTO])
def list_notes(
    due_only: bool = Query(default=False),
    handler: AssetNoteHandler = Depends(get_asset_note_handler),
) -> list[AssetNoteDTO]:
    return [to_note_dto(n, ticker) for n, ticker in handler.list_all(due_only=due_only)]


@notes_router.get("/assets/{asset_id}/notes", response_model=list[AssetNoteDTO])
def list_asset_notes(
    asset_id: int, handler: AssetNoteHandler = Depends(get_asset_note_handler)
) -> list[AssetNoteDTO]:
    return [to_note_dto(n) for n in handler.list_for_asset(asset_id)]


@notes_router.post(
    "/assets/{asset_id}/notes", response_model=AssetNoteDTO, status_code=status.HTTP_201_CREATED
)
def create_asset_note(
    asset_id: int,
    payload: AssetNoteRequest,
    handler: AssetNoteHandler = Depends(get_asset_note_handler),
) -> AssetNoteDTO:
    return to_note_dto(
        handler.create(
            asset_id, payload.text, written_on=payload.written_on, review_at=payload.review_at
        )
    )


@notes_router.put("/assets/{asset_id}/notes/{note_id}", response_model=AssetNoteDTO)
def update_asset_note(
    asset_id: int,
    note_id: int,
    payload: AssetNoteRequest,
    handler: AssetNoteHandler = Depends(get_asset_note_handler),
) -> AssetNoteDTO:
    return to_note_dto(handler.update(asset_id, note_id, payload.text, review_at=payload.review_at))


@notes_router.delete("/assets/{asset_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset_note(
    asset_id: int, note_id: int, handler: AssetNoteHandler = Depends(get_asset_note_handler)
) -> Response:
    handler.delete(asset_id, note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
