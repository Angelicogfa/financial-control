"""SQLAlchemy repositories of the alert rules and the asset notes (Phase 48.R6).

They take and return pure domain entities and never commit
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.watch.entities import AlertRule, AssetNote, RuleMetric, RuleOperator
from domain.watch.repositories import AbstractAlertRuleRepository, AbstractAssetNoteRepository
from infra.data.models.watch import AlertRuleModel, AssetNoteModel


def _rule(m: AlertRuleModel) -> AlertRule:
    return AlertRule(
        id=m.id,
        ticker=m.ticker,
        metric=RuleMetric(m.metric),
        operator=RuleOperator(m.operator),
        threshold=m.threshold,
        is_active=m.is_active,
        note=m.note,
        created_at=m.created_at,
        last_value=m.last_value,
        last_checked_at=m.last_checked_at,
        triggered_at=m.triggered_at,
    )


def _note(m: AssetNoteModel) -> AssetNote:
    return AssetNote(
        id=m.id,
        asset_id=m.asset_id,
        written_on=m.written_on,
        text=m.text,
        review_at=m.review_at,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class SqlAlchemyAlertRuleRepository(AbstractAlertRuleRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self, *, active_only: bool = False) -> list[AlertRule]:
        stmt = select(AlertRuleModel).order_by(AlertRuleModel.ticker, AlertRuleModel.id)
        if active_only:
            stmt = stmt.where(AlertRuleModel.is_active.is_(True))
        return [_rule(m) for m in self.session.scalars(stmt)]

    def get(self, rule_id: int) -> AlertRule | None:
        model = self.session.get(AlertRuleModel, rule_id)
        return _rule(model) if model else None

    def add(self, rule: AlertRule) -> AlertRule:
        model = AlertRuleModel(
            ticker=rule.ticker,
            metric=rule.metric.value,
            operator=rule.operator.value,
            threshold=rule.threshold,
            is_active=rule.is_active,
            note=rule.note,
            created_at=rule.created_at,
        )
        self.session.add(model)
        self.session.flush()
        return _rule(model)

    def update(self, rule: AlertRule) -> AlertRule:
        model = self.session.get(AlertRuleModel, rule.id)
        if model is None:
            raise LookupError(f"alert rule {rule.id} not found")
        model.threshold = rule.threshold
        model.is_active = rule.is_active
        model.note = rule.note
        model.last_value = rule.last_value
        model.last_checked_at = rule.last_checked_at
        model.triggered_at = rule.triggered_at
        self.session.flush()
        return _rule(model)

    def delete(self, rule_id: int) -> bool:
        model = self.session.get(AlertRuleModel, rule_id)
        if model is None:
            return False
        self.session.delete(model)
        self.session.flush()
        return True


class SqlAlchemyAssetNoteRepository(AbstractAssetNoteRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_asset(self, asset_id: int) -> list[AssetNote]:
        stmt = (
            select(AssetNoteModel)
            .where(AssetNoteModel.asset_id == asset_id)
            .order_by(AssetNoteModel.written_on.desc(), AssetNoteModel.id.desc())
        )
        return [_note(m) for m in self.session.scalars(stmt)]

    def list_all(self) -> list[AssetNote]:
        stmt = select(AssetNoteModel).order_by(AssetNoteModel.id)
        return [_note(m) for m in self.session.scalars(stmt)]

    def get(self, note_id: int) -> AssetNote | None:
        model = self.session.get(AssetNoteModel, note_id)
        return _note(model) if model else None

    def add(self, note: AssetNote) -> AssetNote:
        model = AssetNoteModel(
            asset_id=note.asset_id,
            written_on=note.written_on,
            text=note.text,
            review_at=note.review_at,
            created_at=note.created_at,
            updated_at=note.updated_at,
        )
        self.session.add(model)
        self.session.flush()
        return _note(model)

    def update(self, note: AssetNote) -> AssetNote:
        model = self.session.get(AssetNoteModel, note.id)
        if model is None:
            raise LookupError(f"asset note {note.id} not found")
        model.text = note.text
        model.review_at = note.review_at
        model.updated_at = note.updated_at
        self.session.flush()
        return _note(model)

    def delete(self, note_id: int) -> bool:
        model = self.session.get(AssetNoteModel, note_id)
        if model is None:
            return False
        self.session.delete(model)
        self.session.flush()
        return True
