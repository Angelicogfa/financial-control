"""Repository port of the Garimpo (Phase 43)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MiningSignal:
    """One signal of one company in one month (a z against its sector, ±3)."""

    ticker: str
    month: date  # month end
    signal: str  # VALUE, QUALITY, IMPROVEMENT, MOMENTUM; INCOME, RISK (Phase 45.1)
    z: float


@dataclass(frozen=True)
class MiningFinding:
    """One of the best scores of a weekly run (Phase 43.4); never rewritten after the week."""

    found_on: date  # the run's date
    month: date  # month end of the signals used
    rank: int
    ticker: str
    score: float  # monthly return over the class the weights expect, per the signals
    trusted: bool  # the gate had passed: a finding; otherwise a ranking under observation
    signals: dict[str, float]
    reason: str


class AbstractMiningRepository(ABC):
    @abstractmethod
    def replace_signals(self, signals: Sequence[MiningSignal]) -> int:
        """Replace the whole signal panel (it is recomputed every week)."""
        raise NotImplementedError

    @abstractmethod
    def signals_for(self, ticker: str) -> list[MiningSignal]:
        raise NotImplementedError

    @abstractmethod
    def signals_of_month(self, month: date) -> list[MiningSignal]:
        raise NotImplementedError

    @abstractmethod
    def latest_signal_month(self) -> date | None:
        raise NotImplementedError

    @abstractmethod
    def replace_run(self, found_on: date, findings: Sequence[MiningFinding]) -> int:
        """Store a run's findings (a second run the same day replaces that day's)."""
        raise NotImplementedError

    @abstractmethod
    def findings(self, found_on: date | None = None) -> list[MiningFinding]:
        """The findings of a run (the latest by default), best first."""
        raise NotImplementedError

    @abstractmethod
    def all_findings(self) -> list[MiningFinding]:
        """Every past finding, oldest run first (the record)."""
        raise NotImplementedError
