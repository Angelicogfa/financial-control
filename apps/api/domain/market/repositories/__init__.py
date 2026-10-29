"""Repository ports of the market module."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from datetime import date, datetime

from domain.market.entities import (
    AnnouncedDistributions,
    Fundamentals,
    PricePoint,
    Quote,
    QuoteDay,
    StoredMarketData,
)
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

    @abstractmethod
    def save_distributions(
        self, distributions: Mapping[str, AnnouncedDistributions], *, fetched_at: datetime
    ) -> int:
        """Replace the declared distributions of each ticker (an empty one is stored too)."""
        raise NotImplementedError

    @abstractmethod
    def mark_history_loaded(self, tickers: Iterable[str], *, loaded_at: datetime) -> None:
        """Record that the full price history of these tickers is stored."""
        raise NotImplementedError

    @abstractmethod
    def quote_history(
        self, ticker: str, *, date_from: date | None = None, date_to: date | None = None
    ) -> list[QuoteDay]:
        """The last quote of each day, oldest first (audit trail of `save_quotes`)."""
        raise NotImplementedError


class AbstractPriceHistoryRepository(ABC):
    """Daily closes of each ticker, loaded and extended by the worker (Phase 39.2)."""

    @abstractmethod
    def upsert(self, ticker: str, points: Iterable[PricePoint], *, fetched_at: datetime) -> int:
        raise NotImplementedError

    @abstractmethod
    def list_for_many(
        self, tickers: Iterable[str], *, date_from: date | None = None
    ) -> dict[str, list[PricePoint]]:
        """Points of each ticker from `date_from` on, oldest first; empty tickers left out."""
        raise NotImplementedError

    @abstractmethod
    def last_dates(self, tickers: Iterable[str]) -> dict[str, date]:
        raise NotImplementedError


__all__ = [
    "AbstractJobRunRepository",
    "AbstractMarketDataRepository",
    "AbstractPriceHistoryRepository",
    "AbstractMarketSeriesRepository",
]
