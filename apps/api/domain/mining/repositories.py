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
    signal: str  # VALUE, QUALITY, IMPROVEMENT, MOMENTUM
    z: float


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
