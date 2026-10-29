"""Repository port of the simulation runs and results (Phase 33.3)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from domain.simulation.entities import (
    SimulationKind,
    SimulationResult,
    SimulationRun,
    SimulationStudy,
)


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
    def attach(self, run_id: int, *, study_id: int, chapter: str) -> None:
        """Make a run the answer of a study chapter (Phase 41)."""
        raise NotImplementedError

    @abstractmethod
    def list_for_study(self, study_id: int) -> list[SimulationRun]:
        """The runs of a study, oldest first (deleted ones left out)."""
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


class AbstractSimulationStudyRepository(ABC):
    """Studies of the simulation tool (Phase 41); deleted ones are gone for every read."""

    @abstractmethod
    def add(self, study: SimulationStudy) -> SimulationStudy:
        raise NotImplementedError

    @abstractmethod
    def update(self, study: SimulationStudy) -> SimulationStudy:
        raise NotImplementedError

    @abstractmethod
    def get(self, study_id: int) -> SimulationStudy | None:
        raise NotImplementedError

    @abstractmethod
    def list_recent(self, limit: int = 50) -> list[SimulationStudy]:
        """Newest first; only the latest version of each study."""
        raise NotImplementedError

    @abstractmethod
    def versions(self, origin_id: int) -> list[SimulationStudy]:
        """Every version of a study (the origin and its refreshes), oldest first."""
        raise NotImplementedError

    @abstractmethod
    def mark_deleted(self, study_id: int, *, deleted_at: datetime) -> bool:
        raise NotImplementedError
