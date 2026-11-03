"""Entity -> response schema of Acompanhar (Phase 48.R6)."""

from __future__ import annotations

from datetime import date

from contracts.watch.responses import AlertRuleDTO, AssetNoteDTO
from domain.watch.entities import AssetNote, RuleReading
from domain.watch.rules import describe


def to_rule_dto(reading: RuleReading) -> AlertRuleDTO:
    rule = reading.rule
    return AlertRuleDTO(
        id=rule.id or 0,
        ticker=rule.ticker,
        metric=rule.metric,
        operator=rule.operator,
        threshold=float(rule.threshold),
        is_active=rule.is_active,
        note=rule.note,
        description=describe(rule),
        current_value=reading.value,
        triggered=reading.triggered,
        triggered_at=rule.triggered_at,
        last_checked_at=rule.last_checked_at,
        created_at=rule.created_at,
    )


def to_note_dto(
    note: AssetNote, ticker: str | None = None, today: date | None = None
) -> AssetNoteDTO:
    return AssetNoteDTO(
        id=note.id or 0,
        asset_id=note.asset_id,
        ticker=ticker,
        written_on=note.written_on,
        text=note.text,
        review_at=note.review_at,
        due=note.due(today or date.today()),
        created_at=note.created_at,
        updated_at=note.updated_at,
    )
