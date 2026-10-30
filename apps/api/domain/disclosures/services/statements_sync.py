"""Load the statements delivered to the CVM (DFP/ITR) of every listed company (Phase 42.2).

1. The companies are those with a trading code in the FCA map (Phase 28), so the valuation of
   any asset and of its sector can be measured, not only the held ones.
2. The CVM publishes one file per year and kind and rewrites it as statements arrive. The last
   two years are checked on every run (a HEAD request); a file is downloaded again only when its
   Last-Modified changed, and only the statements not stored yet are added (a version never
   changes).
3. The history since 2010 is loaded a few files per run, the oldest missing first, so the first
   load spreads over a few days instead of blocking the worker.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from domain.disclosures.repositories import StatementLoad
from domain.disclosures.statements import DFP, ITR, StatementFact
from domain.shared.unit_of_work import AbstractUnitOfWork

UoWFactory = Callable[[], AbstractUnitOfWork]
FIRST_YEAR = 2010
MAX_FILES_PER_RUN = 4
KINDS = (DFP, ITR)


@dataclass(frozen=True)
class StatementSyncResult:
    companies: int
    loaded: list[str] = field(default_factory=list)  # "DFP 2024: 8479"
    unchanged: int = 0
    missing_years: int = 0  # still to load in later runs
    facts: int = 0

    def as_details(self) -> dict[str, object]:
        return {
            "companies": self.companies,
            "loaded": self.loaded,
            "unchanged": self.unchanged,
            "missing_years": self.missing_years,
            "facts": self.facts,
        }


def plan_files(
    loaded: set[tuple[str, int]], today: date, first_year: int = FIRST_YEAR
) -> list[tuple[str, int]]:
    """Recent files first (always checked), then the oldest missing years."""
    recent = [(kind, year) for year in (today.year, today.year - 1) for kind in KINDS]
    history = [
        (kind, year)
        for year in range(first_year, today.year - 1)
        for kind in KINDS
        if (kind, year) not in loaded
    ]
    return recent + history


def sync_statements(
    uow_factory: UoWFactory,
    *,
    fetch_stamp: Callable[[str, int], str | None],
    fetch_statements: Callable[
        [str, int, set[str], set[tuple[str, date, int]]], list[StatementFact] | None
    ],
    today: date | None = None,
    now: datetime | None = None,
    max_files: int = MAX_FILES_PER_RUN,
    deadline: Callable[[], bool] | None = None,
) -> StatementSyncResult:
    day = today or date.today()
    at = now or datetime.now(UTC)
    with uow_factory() as uow:
        cnpjs = uow.cvm_issuers.all_cnpjs()
        loads = {(load.doc_type, load.year): load for load in uow.cvm_statements.loads()}
    if not cnpjs:
        return StatementSyncResult(companies=0)

    plan = plan_files(set(loads), day)
    loaded: list[str] = []
    unchanged = 0
    total = 0
    downloads = 0
    for kind, year in plan:
        if downloads >= max_files or (deadline is not None and deadline()):
            break
        stamp = fetch_stamp(kind, year)
        if stamp is None:  # not published (the current year's DFP) or unreachable
            continue
        previous = loads.get((kind, year))
        if previous is not None and previous.source_stamp == stamp:
            unchanged += 1
            continue
        with uow_factory() as uow:
            known = uow.cvm_statements.known_docs(kind, year)
        downloads += 1
        facts = fetch_statements(kind, year, cnpjs, known)
        if facts is None:  # download failed: try again next run
            continue
        with uow_factory() as uow:
            added = uow.cvm_statements.add_many(facts)
            uow.cvm_statements.record_load(
                StatementLoad(
                    doc_type=kind,
                    year=year,
                    source_stamp=stamp,
                    facts=(previous.facts if previous else 0) + added,
                    loaded_at=at,
                )
            )
            uow.commit()
        loads[(kind, year)] = StatementLoad(kind, year, stamp, added, at)
        loaded.append(f"{kind} {year}: {added}")
        total += added
    missing = len(plan_files(set(loads), day)) - 2 * len(KINDS)  # history still to load
    return StatementSyncResult(
        companies=len(cnpjs),
        loaded=loaded,
        unchanged=unchanged,
        missing_years=missing,
        facts=total,
    )
