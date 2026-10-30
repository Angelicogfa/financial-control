"""Load the CVM disclosures of every listed company since 2010, for the event study (42.4).

The daily disclosure load (Phase 28.3) keeps only the held and followed companies. The event
study needs the history of every listed company, so this load:

1. checks the IPE files of the last two years on every run (by their Last-Modified) and loads
   the history since 2010 a few years per run, the oldest missing first, as the statements load
   does (42.2);
2. keeps the documents of the companies with a trading code in the CVM map;
3. stores a document delivered more than `STALE_DAYS` before it is first seen as read, the
   same rule as the daily load, so the unread count and the alerts stay about what is new;
4. classifies the stored documents that were never classified (event_class NULL).

The yearly loads are recorded in `cvm_statement_loads` with the kind `IPE`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta

from domain.disclosures.entities import CvmDocument
from domain.disclosures.events import classify
from domain.disclosures.repositories import StatementLoad
from domain.disclosures.services.statements_sync import FIRST_YEAR
from domain.disclosures.services.sync import STALE_DAYS
from domain.shared.unit_of_work import AbstractUnitOfWork

UoWFactory = Callable[[], AbstractUnitOfWork]
IPE = "IPE"
MAX_FILES_PER_RUN = 5
CLASSIFY_BATCH = 5000


@dataclass(frozen=True)
class EventHistoryResult:
    companies: int
    loaded: list[str] = field(default_factory=list)  # "IPE 2015: 1234"
    unchanged: int = 0
    missing_years: int = 0
    classified: int = 0

    def as_details(self) -> dict[str, object]:
        return {
            "companies": self.companies,
            "loaded": self.loaded,
            "unchanged": self.unchanged,
            "missing_years": self.missing_years,
            "classified": self.classified,
        }


def plan_years(loaded: set[int], today: date, first_year: int = FIRST_YEAR) -> list[int]:
    recent = [today.year, today.year - 1]
    history = [y for y in range(first_year, today.year - 1) if y not in loaded]
    return recent + history


def classify_missing(uow: AbstractUnitOfWork, limit: int = CLASSIFY_BATCH) -> int:
    docs = uow.cvm_documents.unclassified(limit)
    classes = {
        d.id: classify(d.category, d.doc_type, d.subject) or "" for d in docs if d.id is not None
    }
    return uow.cvm_documents.set_event_classes(classes) if classes else 0


def sync_event_history(
    uow_factory: UoWFactory,
    *,
    fetch_stamp: Callable[[int], str | None],
    fetch_documents: Callable[[int], list[CvmDocument]],
    today: date | None = None,
    now: datetime | None = None,
    max_files: int = MAX_FILES_PER_RUN,
    deadline: Callable[[], bool] | None = None,
) -> EventHistoryResult:
    day = today or date.today()
    seen_at = now or datetime.now(UTC)
    with uow_factory() as uow:
        cnpjs = uow.cvm_issuers.all_cnpjs()
        loads = {load.year: load for load in uow.cvm_statements.loads() if load.doc_type == IPE}
        classified = classify_missing(uow)
        uow.commit()
    if not cnpjs:
        return EventHistoryResult(companies=0, classified=classified)

    stale_before = day - timedelta(days=STALE_DAYS)
    loaded: list[str] = []
    unchanged = downloads = 0
    for year in plan_years(set(loads), day):
        if downloads >= max_files or (deadline is not None and deadline()):
            break
        stamp = fetch_stamp(year)
        if stamp is None:
            continue
        previous = loads.get(year)
        if previous is not None and previous.source_stamp == stamp:
            unchanged += 1
            continue
        downloads += 1
        found = [
            replace(d, read_at=seen_at)
            if d.delivery_date < stale_before and d.read_at is None
            else d
            for d in fetch_documents(year)
            if d.cnpj in cnpjs
        ]
        if not found:
            continue
        with uow_factory() as uow:
            new = uow.cvm_documents.upsert_many(found, seen_at=seen_at)
            uow.cvm_statements.record_load(
                StatementLoad(
                    doc_type=IPE, year=year, source_stamp=stamp, facts=len(found), loaded_at=seen_at
                )
            )
            uow.commit()
        loads[year] = StatementLoad(IPE, year, stamp, len(found), seen_at)
        loaded.append(f"IPE {year}: {new}")
    missing = len(plan_years(set(loads), day)) - 2
    return EventHistoryResult(
        companies=len(cnpjs),
        loaded=loaded,
        unchanged=unchanged,
        missing_years=missing,
        classified=classified,
    )
