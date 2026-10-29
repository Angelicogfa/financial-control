"""Repository ports of the market module."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from datetime import datetime

from domain.market.entities import Fundamentals, Quote, StoredMarketData
from domain.shared.repositories import AbstractJobRunRepository, AbstractMarketSeriesRepository


class AbstractMarketDataRepository(ABC):
    """Last quote and fundamentals per ticker, written by the worker and read by the screens."""

    @abstractmethod
    def get_many(self, tickers: Iterable[str]) -> dict[str, StoredMarketData]:
        """Stored data of each ticker that has any; tickers never fetched are left out."""
        raise NotImplementedError

    @abstractmethod
    def save_quotes(self, quotes: Mapping[str, Quote], *, fetched_at: datetime) -> int:
        """Replace the stored quote of each ticker; other tickers keep theirs."""
        raise NotImplementedError

    @abstractmethod
    def save_fundamentals(
        self, fundamentals: Mapping[str, Fundamentals], *, fetched_at: datetime
    ) -> int:
        """Replace the stored fundamentals of each ticker; other tickers keep theirs."""
        raise NotImplementedError


__all__ = [
    "AbstractJobRunRepository",
    "AbstractMarketDataRepository",
    "AbstractMarketSeriesRepository",
]
