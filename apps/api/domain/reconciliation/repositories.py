"""Repository port of the position reconciliations (Phase 48.R5)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from domain.reconciliation.entities import PositionReconciliation, ReconciliationLine


class AbstractReconciliationRepository(ABC):
    @abstractmethod
    def add(self, reconciliation: PositionReconciliation) -> PositionReconciliation: ...

    @abstractmethod
    def get(self, reconciliation_id: int) -> PositionReconciliation | None: ...

    @abstractmethod
    def find(self, reference_date: date, file_hash: str) -> PositionReconciliation | None:
        """The reconciliation of this same file and date, if it was already saved."""

    @abstractmethod
    def list_recent(self, limit: int = 20) -> list[PositionReconciliation]:
        """Newest first, by reference date and then by creation."""

    @abstractmethod
    def update_line(self, line: ReconciliationLine) -> ReconciliationLine: ...
