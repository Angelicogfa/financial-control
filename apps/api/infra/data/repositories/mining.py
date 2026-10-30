"""SQLAlchemy repository of the Garimpo (Phase 43).

It takes and returns pure domain entities and never commits
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from domain.mining.repositories import AbstractMiningRepository, MiningSignal
from infra.data.models.mining import MiningSignalModel

CHUNK = 500


def _signal(m: MiningSignalModel) -> MiningSignal:
    return MiningSignal(ticker=m.ticker, month=m.month, signal=m.signal, z=m.z)


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
