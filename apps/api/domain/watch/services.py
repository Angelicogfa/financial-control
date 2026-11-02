"""Use cases of Acompanhar (Phase 48.R6): alert rules on any ticker and the thesis notes.

Rules are read against the database (no provider call); the worker job `evaluate_alert_rules`
keeps the last value and when each rule last fired. Notes never touch the ledger.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from core.errors import NotFoundError, ValidationError
from domain.alerts.services.evaluator import Alert, AlertKind, AlertSeverity
from domain.instruments.read_models import InstrumentKind, instrument_key
from domain.shared.unit_of_work import AbstractUnitOfWork, UoWFactory
from domain.watch.entities import AlertRule, AssetNote, RuleMetric, RuleOperator, RuleReading
from domain.watch.rules import describe, read_rules, reading_detail

MAX_RULES = 200
MAX_NOTE_LENGTH = 4000


def current_readings(uow: AbstractUnitOfWork, *, active_only: bool = False) -> list[RuleReading]:
    rules = uow.alert_rules.list_all(active_only=active_only)
    tickers = sorted({r.ticker for r in rules})
    stored = uow.market_data.get_many(tickers) if tickers else {}
    catalog = {t: c for t in tickers if (c := uow.catalog.get(t)) is not None}
    return read_rules(rules, stored, catalog)


def rule_alerts(readings: list[RuleReading]) -> list[Alert]:
    """Each active rule that holds now becomes an ordinary alert of the Início."""
    return [
        Alert(
            f"rule:{r.rule.id}",
            AlertKind.USER_RULE,
            AlertSeverity.WARNING,
            describe(r.rule),
            reading_detail(r) + (f" {r.rule.note}" if r.rule.note else ""),
            r.rule.ticker,
            f"/ativo/{r.rule.ticker}",
        )
        for r in readings
        if r.triggered
    ]


def thesis_alerts(notes: list[AssetNote], tickers: dict[int, str], today: date) -> list[Alert]:
    """A thesis whose review date arrived: look at it again."""
    alerts = []
    for note in notes:
        if not note.due(today) or note.asset_id not in tickers:
            continue
        ticker = tickers[note.asset_id]
        alerts.append(
            Alert(
                f"thesis:{note.id}:{note.review_at.isoformat() if note.review_at else ''}",
                AlertKind.THESIS_REVIEW,
                AlertSeverity.INFO,
                f"Revisar a tese de {ticker}",
                note.text[:160] + ("…" if len(note.text) > 160 else ""),
                ticker,
                f"/ativo/{ticker}?capitulo=tese",
            )
        )
    return alerts


class AlertRuleHandler:
    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def list(self) -> list[RuleReading]:
        with self.uow_factory() as uow:
            return current_readings(uow)

    def create(
        self,
        ticker: str,
        metric: RuleMetric,
        operator: RuleOperator,
        threshold: Decimal,
        note: str | None = None,
    ) -> RuleReading:
        key = instrument_key(ticker)
        if key.kind != InstrumentKind.LISTED:
            raise ValidationError("Alert rules take a trading code", code="INVALID_INSTRUMENT")
        if threshold < 0:
            raise ValidationError("The threshold cannot be negative", code="INVALID_THRESHOLD")
        with self.uow_factory() as uow:
            known = (
                uow.catalog.get(key.value) is not None
                or uow.assets.get_by_ticker(key.value) is not None
                or key.value in uow.market_data.get_many([key.value])
            )
            if not known:
                raise NotFoundError(
                    f"Instrument {key.value} not found", code="INSTRUMENT_NOT_FOUND"
                )
            if len(uow.alert_rules.list_all()) >= MAX_RULES:
                raise ValidationError(f"At most {MAX_RULES} alert rules", code="TOO_MANY_RULES")
            saved = uow.alert_rules.add(
                AlertRule(
                    ticker=key.value,
                    metric=metric,
                    operator=operator,
                    threshold=threshold,
                    note=(note or "").strip() or None,
                    created_at=datetime.now(UTC),
                )
            )
            uow.commit()
            return next(r for r in current_readings(uow) if r.rule.id == saved.id)

    def update(
        self,
        rule_id: int,
        *,
        threshold: Decimal | None = None,
        is_active: bool | None = None,
        note: str | None = None,
    ) -> RuleReading:
        with self.uow_factory() as uow:
            rule = uow.alert_rules.get(rule_id)
            if rule is None:
                raise NotFoundError(f"Alert rule id={rule_id} not found")
            if threshold is not None and threshold < 0:
                raise ValidationError("The threshold cannot be negative", code="INVALID_THRESHOLD")
            uow.alert_rules.update(
                replace(
                    rule,
                    threshold=threshold if threshold is not None else rule.threshold,
                    is_active=is_active if is_active is not None else rule.is_active,
                    note=rule.note if note is None else (note.strip() or None),
                )
            )
            uow.commit()
            return next(r for r in current_readings(uow) if r.rule.id == rule_id)

    def delete(self, rule_id: int) -> None:
        with self.uow_factory() as uow:
            if not uow.alert_rules.delete(rule_id):
                raise NotFoundError(f"Alert rule id={rule_id} not found")
            uow.commit()


def evaluate_alert_rules(uow: AbstractUnitOfWork, *, now: datetime) -> dict[str, int]:
    """Worker side: keep the last value and when each active rule became true."""
    fired = checked = 0
    for reading in current_readings(uow, active_only=True):
        rule = reading.rule
        triggered_at = rule.triggered_at
        if reading.triggered and triggered_at is None:
            triggered_at = now
            fired += 1
        elif not reading.triggered:
            triggered_at = None
        uow.alert_rules.update(
            replace(
                rule,
                last_value=Decimal(str(reading.value)) if reading.value is not None else None,
                last_checked_at=now,
                triggered_at=triggered_at,
            )
        )
        checked += 1
    return {"checked": checked, "fired": fired}


class AssetNoteHandler:
    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    @staticmethod
    def _text(text: str) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            raise ValidationError("The note cannot be empty", code="EMPTY_NOTE")
        if len(cleaned) > MAX_NOTE_LENGTH:
            raise ValidationError(f"Notes have at most {MAX_NOTE_LENGTH} characters")
        return cleaned

    def list_for_asset(self, asset_id: int) -> list[AssetNote]:
        with self.uow_factory() as uow:
            if uow.assets.get_by_id(asset_id) is None:
                raise NotFoundError(f"Asset id={asset_id} not found")
            return uow.asset_notes.list_for_asset(asset_id)

    def list_all(
        self, *, due_only: bool = False, today: date | None = None
    ) -> list[tuple[AssetNote, str]]:
        """Every note with its ticker, the due ones first (oldest review first)."""
        on = today or date.today()
        with self.uow_factory() as uow:
            tickers = {a.id: a.ticker for a in uow.assets.list_all(active_only=False) if a.id}
            notes = [n for n in uow.asset_notes.list_all() if n.asset_id in tickers]
        if due_only:
            notes = [n for n in notes if n.due(on)]
        notes.sort(key=lambda n: (not n.due(on), n.review_at or date.max, -(n.id or 0)))
        return [(n, tickers[n.asset_id]) for n in notes]

    def create(
        self,
        asset_id: int,
        text: str,
        *,
        written_on: date | None = None,
        review_at: date | None = None,
    ) -> AssetNote:
        cleaned = self._text(text)
        on = written_on or date.today()
        if review_at is not None and review_at < on:
            raise ValidationError(
                "The review date comes after the note", code="INVALID_REVIEW_DATE"
            )
        with self.uow_factory() as uow:
            if uow.assets.get_by_id(asset_id) is None:
                raise NotFoundError(f"Asset id={asset_id} not found")
            now = datetime.now(UTC)
            saved = uow.asset_notes.add(
                AssetNote(
                    asset_id=asset_id,
                    written_on=on,
                    text=cleaned,
                    review_at=review_at,
                    created_at=now,
                    updated_at=now,
                )
            )
            uow.commit()
        return saved

    def update(
        self, asset_id: int, note_id: int, text: str, *, review_at: date | None = None
    ) -> AssetNote:
        cleaned = self._text(text)
        with self.uow_factory() as uow:
            note = uow.asset_notes.get(note_id)
            if note is None or note.asset_id != asset_id:
                raise NotFoundError(f"Note id={note_id} of asset {asset_id} not found")
            if review_at is not None and review_at < note.written_on:
                raise ValidationError(
                    "The review date comes after the note", code="INVALID_REVIEW_DATE"
                )
            saved = uow.asset_notes.update(
                replace(note, text=cleaned, review_at=review_at, updated_at=datetime.now(UTC))
            )
            uow.commit()
        return saved

    def delete(self, asset_id: int, note_id: int) -> None:
        with self.uow_factory() as uow:
            note = uow.asset_notes.get(note_id)
            if note is None or note.asset_id != asset_id:
                raise NotFoundError(f"Note id={note_id} of asset {asset_id} not found")
            uow.asset_notes.delete(note_id)
            uow.commit()
