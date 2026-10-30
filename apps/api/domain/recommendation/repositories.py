"""Repository port of the recommendation (Phase 45)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import date

from domain.recommendation.gates import AssetGates
from domain.recommendation.lenses import AssetLenses


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
