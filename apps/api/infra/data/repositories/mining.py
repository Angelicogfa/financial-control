"""SQLAlchemy repository of the Garimpo (Phase 43).

It takes and returns pure domain entities and never commits
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from domain.mining.repositories import AbstractMiningRepository, MiningFinding, MiningSignal
from infra.data.models.mining import MiningFindingModel, MiningSignalModel

CHUNK = 500


def _signal(m: MiningSignalModel) -> MiningSignal:
    return MiningSignal(ticker=m.ticker, month=m.month, signal=m.signal, z=m.z)


def _finding(m: MiningFindingModel) -> MiningFinding:
    return MiningFinding(
        found_on=m.found_on,
        month=m.month,
        rank=m.rank,
        ticker=m.ticker,
        score=m.score,
        trusted=m.trusted,
        signals=dict(m.signals),
        reason=m.reason,
    )


class SqlAlchemyMiningRepository(AbstractMiningRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_signals(self, signals: Sequence[MiningSignal]) -> int:
        self.session.execute(delete(MiningSignalModel))
        rows = [
            {"ticker": s.ticker, "month": s.month, "signal": s.signal, "z": s.z} for s in signals
        ]
        for i in range(0, len(rows), CHUNK):
            self.session.execute(insert(MiningSignalModel), rows[i : i + CHUNK])
        self.session.flush()
        return len(rows)

    def signals_for(self, ticker: str) -> list[MiningSignal]:
        stmt = (
            select(MiningSignalModel)
            .where(MiningSignalModel.ticker == ticker.strip().upper())
            .order_by(MiningSignalModel.month, MiningSignalModel.signal)
        )
        return [_signal(m) for m in self.session.scalars(stmt).all()]

    def signals_of_month(self, month: date) -> list[MiningSignal]:
        stmt = (
            select(MiningSignalModel)
            .where(MiningSignalModel.month == month)
            .order_by(MiningSignalModel.ticker, MiningSignalModel.signal)
        )
        return [_signal(m) for m in self.session.scalars(stmt).all()]

    def latest_signal_month(self) -> date | None:
        return self.session.scalar(select(func.max(MiningSignalModel.month)))

    def replace_run(self, found_on: date, findings: Sequence[MiningFinding]) -> int:
        self.session.execute(
            delete(MiningFindingModel).where(MiningFindingModel.found_on == found_on)
        )
        for f in findings:
            self.session.add(
                MiningFindingModel(
                    found_on=found_on,
                    month=f.month,
                    rank=f.rank,
                    ticker=f.ticker,
                    score=f.score,
                    trusted=f.trusted,
                    signals=dict(f.signals),
                    reason=f.reason,
                )
            )
        self.session.flush()
        return len(findings)

    def findings(self, found_on: date | None = None) -> list[MiningFinding]:
        day = found_on or self.session.scalar(select(func.max(MiningFindingModel.found_on)))
        if day is None:
            return []
        stmt = (
            select(MiningFindingModel)
            .where(MiningFindingModel.found_on == day)
            .order_by(MiningFindingModel.rank)
        )
        return [_finding(m) for m in self.session.scalars(stmt).all()]

    def all_findings(self) -> list[MiningFinding]:
        stmt = select(MiningFindingModel).order_by(
            MiningFindingModel.found_on, MiningFindingModel.rank
        )
        return [_finding(m) for m in self.session.scalars(stmt).all()]
