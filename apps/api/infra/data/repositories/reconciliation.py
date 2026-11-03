"""SQLAlchemy repository of the position checks (Phase 48.R5).

It takes and returns pure domain entities and never commits
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from domain.reconciliation.entities import (
    LineResolution,
    LineStatus,
    PositionReconciliation,
    ReconciliationLine,
)
from domain.reconciliation.repositories import AbstractReconciliationRepository
from infra.data.models.reconciliation import (
    PositionReconciliationLineModel,
    PositionReconciliationModel,
)


def _line(m: PositionReconciliationLineModel) -> ReconciliationLine:
    return ReconciliationLine(
        id=m.id,
        product=m.product,
        ticker=m.ticker,
        asset_id=m.asset_id,
        account_id=m.account_id,
        institution=m.institution,
        b3_quantity=m.b3_quantity,
        ledger_quantity=m.ledger_quantity,
        status=LineStatus(m.status),
        note=m.note or "",
        resolution=LineResolution(m.resolution),
        resolution_note=m.resolution_note,
        resolved_at=m.resolved_at,
    )


def _entity(m: PositionReconciliationModel) -> PositionReconciliation:
    return PositionReconciliation(
        id=m.id,
        reference_date=m.reference_date,
        file_name=m.file_name,
        file_hash=m.file_hash,
        created_at=m.created_at,
        lines=[_line(line) for line in m.lines],
    )


class SqlAlchemyReconciliationRepository(AbstractReconciliationRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def _query(self):
        return select(PositionReconciliationModel).options(
            selectinload(PositionReconciliationModel.lines)
        )

    def add(self, reconciliation: PositionReconciliation) -> PositionReconciliation:
        model = PositionReconciliationModel(
            reference_date=reconciliation.reference_date,
            file_name=reconciliation.file_name[:255],
            file_hash=reconciliation.file_hash,
            created_at=reconciliation.created_at,
            lines=[
                PositionReconciliationLineModel(
                    product=line.product[:64],
                    ticker=line.ticker,
                    asset_id=line.asset_id,
                    account_id=line.account_id,
                    institution=(line.institution or None) and line.institution[:255],
                    b3_quantity=line.b3_quantity,
                    ledger_quantity=line.ledger_quantity,
                    status=line.status.value,
                    note=line.note,
                    resolution=line.resolution.value,
                    resolution_note=line.resolution_note,
                    resolved_at=line.resolved_at,
                )
                for line in reconciliation.lines
            ],
        )
        self.session.add(model)
        self.session.flush()
        return _entity(model)

    def get(self, reconciliation_id: int) -> PositionReconciliation | None:
        model = self.session.scalars(
            self._query().where(PositionReconciliationModel.id == reconciliation_id)
        ).first()
        return _entity(model) if model else None

    def find(self, reference_date: date, file_hash: str) -> PositionReconciliation | None:
        model = self.session.scalars(
            self._query().where(
                PositionReconciliationModel.reference_date == reference_date,
                PositionReconciliationModel.file_hash == file_hash,
            )
        ).first()
        return _entity(model) if model else None

    def list_recent(self, limit: int = 20) -> list[PositionReconciliation]:
        stmt = (
            self._query()
            .order_by(
                PositionReconciliationModel.reference_date.desc(),
                PositionReconciliationModel.id.desc(),
            )
            .limit(limit)
        )
        return [_entity(m) for m in self.session.scalars(stmt)]

    def update_line(self, line: ReconciliationLine) -> ReconciliationLine:
        model = self.session.get(PositionReconciliationLineModel, line.id)
        if model is None:
            raise LookupError(f"reconciliation line {line.id} not found")
        model.resolution = line.resolution.value
        model.resolution_note = line.resolution_note
        model.resolved_at = line.resolved_at
        self.session.flush()
        return _line(model)
