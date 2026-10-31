"""Repository port of the recommendation (Phase 45)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from domain.recommendation.combination import ClassMatrix
from domain.recommendation.construction import ClassConstruction
from domain.recommendation.gates import AssetGates
from domain.recommendation.lenses import AssetLenses


@dataclass(frozen=True)
class RecommendationRun:
    """One weekly run of the recommendation (Phase 45.5): what it used and what it chose.

    The lenses, gates, matrices and constructions of the same date hold the detail; this is the
    entry of the history, with the policy version the run applied.
    """

    as_of: date
    policy_version: int | None
    signal_month: date | None
    assets: int
    eligible: int
    selected: dict[str, list[str]] = field(default_factory=dict)  # class -> chosen tickers


class AbstractRecommendationRepository(ABC):
    @abstractmethod
    def replace_lenses(self, as_of: date, items: Sequence[AssetLenses]) -> int:
        """Store the lenses of a run (a second run the same day replaces that day's)."""
        raise NotImplementedError

    @abstractmethod
    def latest_lens_date(self) -> date | None:
        raise NotImplementedError

    @abstractmethod
    def lenses(
        self, as_of: date | None = None, tickers: Sequence[str] | None = None
    ) -> list[AssetLenses]:
        """The lenses of a run (the latest by default), optionally of some tickers."""
        raise NotImplementedError

    @abstractmethod
    def replace_gates(self, as_of: date, items: Sequence[AssetGates]) -> int:
        """Store the gates of a run (a second run the same day replaces that day's)."""
        raise NotImplementedError

    @abstractmethod
    def gates(
        self, as_of: date | None = None, tickers: Sequence[str] | None = None
    ) -> list[AssetGates]:
        """The gates of a run (the latest lens run by default), optionally of some tickers."""
        raise NotImplementedError

    @abstractmethod
    def replace_matrices(
        self,
        as_of: date,
        items: Sequence[ClassMatrix],
        constructions: Mapping[str, ClassConstruction] | None = None,
    ) -> int:
        """Store the decision matrix of each class and its construction (45.4), replacing the
        same day's."""
        raise NotImplementedError

    @abstractmethod
    def constructions(self, as_of: date | None = None) -> list[ClassConstruction]:
        """The weight constructions of a run (the latest lens run by default)."""
        raise NotImplementedError

    @abstractmethod
    def matrices(self, as_of: date | None = None) -> list[ClassMatrix]:
        """The decision matrices of a run (the latest lens run by default)."""
        raise NotImplementedError

    @abstractmethod
    def save_run(self, run: RecommendationRun) -> None:
        """Store a run (a second run the same day replaces that day's)."""
        raise NotImplementedError

    @abstractmethod
    def runs(self, limit: int = 52) -> list[RecommendationRun]:
        """The latest runs, newest first."""
        raise NotImplementedError
