"""Position check against the B3 Posição statement (Phase 48.R5, REFACTORING_PLAN §3.5).

A reconciliation never writes to the ledger: it points at each difference, per ticker and
custody account, and the investor fixes the ledger (or marks the line as explained).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class LineStatus(StrEnum):
    MATCH = "MATCH"  # same quantity in the statement and in the ledger
    DIVERGENT = "DIVERGENT"  # both have it, with different quantities
    ONLY_B3 = "ONLY_B3"  # the statement has it, the ledger does not
    ONLY_LEDGER = "ONLY_LEDGER"  # the ledger has it, the statement does not
    NOT_COMPARED = "NOT_COMPARED"  # no trading code (Tesouro, bank fixed income): shown only


class LineResolution(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"  # the investor fixed the ledger or explained the difference


NEEDS_ACTION = frozenset({LineStatus.DIVERGENT, LineStatus.ONLY_B3, LineStatus.ONLY_LEDGER})


@dataclass(frozen=True)
class StatementPosition:
    """One row of the Posição statement."""

    product: str  # sheet of the statement: Ações, BDR, ETF, Fundo de Investimento, Tesouro…
    description: str
    quantity: Decimal
    ticker: str | None = None
    institution: str | None = None


@dataclass
class ReconciliationLine:
    product: str
    b3_quantity: Decimal
    ledger_quantity: Decimal
    status: LineStatus
    ticker: str | None = None
    asset_id: int | None = None
    account_id: int | None = None
    # The institution as B3 writes it, or the account name for ledger-only lines.
    institution: str | None = None
    note: str = ""
    resolution: LineResolution = LineResolution.OPEN
    resolution_note: str | None = None
    resolved_at: datetime | None = None
    id: int | None = None

    @property
    def difference(self) -> Decimal:
        return self.b3_quantity - self.ledger_quantity


@dataclass
class PositionReconciliation:
    reference_date: date
    file_name: str
    file_hash: str
    lines: list[ReconciliationLine] = field(default_factory=list)
    created_at: datetime | None = None
    id: int | None = None

    def count(self, status: LineStatus) -> int:
        return sum(1 for line in self.lines if line.status == status)

    @property
    def open_issues(self) -> int:
        return sum(
            1
            for line in self.lines
            if line.status in NEEDS_ACTION and line.resolution == LineResolution.OPEN
        )
