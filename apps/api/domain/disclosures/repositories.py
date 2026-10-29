"""Repository ports of the CVM disclosures (Phase 28)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import date, datetime

from domain.disclosures.entities import CvmDocument, IssuerTicker


class AbstractIssuerTickerRepository(ABC):
    @abstractmethod
    def replace_all(self, items: Sequence[IssuerTicker]) -> int:
        """Store the ticker map (the newest FCA wins); returns how many tickers it has."""
        raise NotImplementedError

    @abstractmethod
    def cnpjs_for(self, tickers: Sequence[str]) -> dict[str, str]:
        """Ticker -> CNPJ (digits) for the tickers found."""
        raise NotImplementedError


class AbstractCvmDocumentRepository(ABC):
    @abstractmethod
    def upsert_many(self, documents: Sequence[CvmDocument], *, seen_at: datetime) -> int:
        """Insert new protocols and replace older versions; returns how many were new."""
        raise NotImplementedError

    @abstractmethod
    def list(
        self,
        cnpjs: Sequence[str],
        *,
        categories: Sequence[str] = (),
        unread_only: bool = False,
        since: date | None = None,
        limit: int = 50,
    ) -> list[CvmDocument]:
        """Newest delivery first."""
        raise NotImplementedError

    @abstractmethod
    def count_unread(self, cnpjs: Sequence[str], *, categories: Sequence[str] = ()) -> int:
        raise NotImplementedError

    @abstractmethod
    def category_counts(self, cnpjs: Sequence[str]) -> dict[str, int]:
        raise NotImplementedError

    @abstractmethod
    def mark_read(self, ids: Sequence[int], *, read_at: datetime) -> int:
        raise NotImplementedError

    @abstractmethod
    def mark_all_read(self, cnpjs: Sequence[str], *, read_at: datetime) -> int:
        raise NotImplementedError

    @abstractmethod
    def latest_delivery(self) -> date | None:
        raise NotImplementedError
