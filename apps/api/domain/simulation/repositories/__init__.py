"""Repository port of the simulation runs and results (Phase 33.3)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from domain.simulation.entities import SimulationKind, SimulationResult, SimulationRun


class AbstractSimulationRepository(ABC):
    @abstractmethod
    def add(self, run: SimulationRun) -> SimulationRun:
        raise NotImplementedError

    @abstractmethod
    def update(self, run: SimulationRun) -> SimulationRun:
        raise NotImplementedError

    @abstractmethod
    def get(self, run_id: int) -> SimulationRun | None:
        raise NotImplementedError

    @abstractmethod
    def list_recent(
        self, limit: int = 20, kind: SimulationKind | None = None
    ) -> list[SimulationRun]:
        """Newest first, optionally of one kind."""
        raise NotImplementedError

    @abstractmethod
    def mark_deleted(self, run_id: int, *, deleted_at: datetime) -> bool:
        """Hide a run for good (Phase 40.4); False when it does not exist or is already gone."""
        raise NotImplementedError

    @abstractmethod
    def next_pending(self) -> SimulationRun | None:
        """Oldest run waiting to be executed."""
        raise NotImplementedError

    @abstractmethod
    def find_done(
        self, params_hash: str, data_hash: str, code_version: str
    ) -> SimulationRun | None:
        """A finished run with the same inputs and code (reproducibility cache)."""
        raise NotImplementedError

    @abstractmethod
    def save_results(self, run_id: int, results: list[SimulationResult]) -> None:
        """Replace the results of a run."""
        raise NotImplementedError

    @abstractmethod
    def results(self, run_id: int) -> list[SimulationResult]:
        raise NotImplementedError

    @abstractmethod
    def count_results(self, key_prefix: str) -> int:
        """Results whose key starts with the prefix, over runs actually computed (not reused)."""
        raise NotImplementedError
