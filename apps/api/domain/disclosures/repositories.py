"""Repository ports of the CVM disclosures (Phase 28)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from domain.disclosures.entities import CvmDocument, EventEffect, IssuerTicker
from domain.disclosures.statements import StatementDoc, StatementFact


class AbstractIssuerTickerRepository(ABC):
    @abstractmethod
    def replace_all(self, items: Sequence[IssuerTicker]) -> int:
        """Store the ticker map (the newest FCA wins); returns how many tickers it has."""
        raise NotImplementedError

    @abstractmethod
    def cnpjs_for(self, tickers: Sequence[str]) -> dict[str, str]:
        """Ticker -> CNPJ (digits) for the tickers found."""
        raise NotImplementedError

    @abstractmethod
    def all_cnpjs(self) -> set[str]:
        """Every company with a trading code in the map."""
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
    def unclassified(self, limit: int) -> list[CvmDocument]:
        """Documents never classified (event_class is None), oldest first."""
        raise NotImplementedError

    @abstractmethod
    def set_event_classes(self, classes: dict[int, str]) -> int:
        raise NotImplementedError

    @abstractmethod
    def events(self, cnpjs: Sequence[str] | None = None) -> list[CvmDocument]:
        """Documents that are events (a non-empty class), oldest first."""
        raise NotImplementedError

    @abstractmethod
    def replace_effects(self, effects: Sequence[EventEffect]) -> int:
        """Replace the measured reactions (recomputed every week)."""
        raise NotImplementedError

    @abstractmethod
    def effects(self, document_ids: Sequence[int] | None = None) -> list[EventEffect]:
        raise NotImplementedError

    @abstractmethod
    def latest_delivery(self) -> date | None:
        raise NotImplementedError


@dataclass(frozen=True)
class StatementLoad:
    """A yearly CVM statement file already loaded, and the version of the file it came from."""

    doc_type: str
    year: int
    source_stamp: str  # Last-Modified of the file: a new one means new deliveries
    facts: int
    loaded_at: datetime


class AbstractCvmStatementRepository(ABC):
    @abstractmethod
    def known_docs(self, doc_type: str, year: int) -> set[tuple[str, date, int]]:
        """(cnpj, reference date, version) already stored for the statements of that year."""
        raise NotImplementedError

    @abstractmethod
    def add_many(self, facts: Sequence[StatementFact]) -> int:
        """Store the facts of statements not stored yet (a version never changes)."""
        raise NotImplementedError

    @abstractmethod
    def facts_for(self, cnpj: str) -> list[StatementFact]:
        raise NotImplementedError

    @abstractmethod
    def cnpjs_with_statements(self) -> set[str]:
        """Companies with at least one stored statement."""
        raise NotImplementedError

    @abstractmethod
    def docs_for(self, cnpj: str) -> list[StatementDoc]:
        """The delivered statements of a company, every version."""
        raise NotImplementedError

    @abstractmethod
    def record_load(self, load: StatementLoad) -> None:
        raise NotImplementedError

    @abstractmethod
    def loads(self) -> list[StatementLoad]:
        raise NotImplementedError
