"""SQLAlchemy implementation of AbstractUnitOfWork."""

from __future__ import annotations

from types import TracebackType

from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork
from sqlalchemy.orm import Session, sessionmaker

from fincontrol_persistence.db import get_default_session_factory
from fincontrol_persistence.repositories import (
    SqlAlchemyArcaTargetRepository,
    SqlAlchemyAssetRepository,
    SqlAlchemyEarningRepository,
    SqlAlchemyMarketSeriesRepository,
    SqlAlchemyPortfolioSnapshotRepository,
    SqlAlchemyTransactionRepository,
)


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """Concrete Unit of Work managing a SQLAlchemy Session and all domain repositories."""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory or get_default_session_factory()
        self.session: Session | None = None

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self.session = self._session_factory()
        self.assets = SqlAlchemyAssetRepository(self.session)
        self.transactions = SqlAlchemyTransactionRepository(self.session)
        self.earnings = SqlAlchemyEarningRepository(self.session)
        self.arca_targets = SqlAlchemyArcaTargetRepository(self.session)
        self.market_series = SqlAlchemyMarketSeriesRepository(self.session)
        self.snapshots = SqlAlchemyPortfolioSnapshotRepository(self.session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            super().__exit__(exc_type, exc_val, exc_tb)
        finally:
            if self.session is not None:
                self.session.close()
                self.session = None

    def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("Cannot commit outside an active UnitOfWork context")
        self.session.commit()

    def rollback(self) -> None:
        if self.session is not None:
            self.session.rollback()
