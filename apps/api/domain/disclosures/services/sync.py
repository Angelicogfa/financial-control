"""Load the CVM disclosures of the held and followed companies (Phase 28.3).

1. Refresh the ticker -> CNPJ map from the FCA of the last years (the newest wins). A failed
   download keeps the stored map instead of wiping it.
2. Find the CNPJ of every active Brazilian stock (portfolio and watchlist). FIIs and ETFs are
   not companies and have no IPE filings (28.5).
3. Download the IPE of the current year (and the previous one on the first run and in
   January, for late filings) and keep only the documents of those companies.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from domain.disclosures.entities import CvmDocument, IssuerTicker
from domain.shared.entities import AssetEntity
from domain.shared.enums import AssetType
from domain.shared.unit_of_work import AbstractUnitOfWork

UoWFactory = Callable[[], AbstractUnitOfWork]
COMPANY_TYPES = frozenset({AssetType.STOCK_BR})
FCA_YEARS = 3
MAX_LISTED_UNMAPPED = 20


def company_assets(assets: Sequence[AssetEntity]) -> list[AssetEntity]:
    """Active Brazilian stocks: the only assets with IPE filings."""
    return [a for a in assets if a.asset_type in COMPANY_TYPES]


def base_ticker(ticker: str) -> str:
    """Odd-lot tickers trade as the main code (PETR4F -> PETR4)."""
    code = ticker.strip().upper()
    return code[:-1] if code.endswith("F") and code[:-1][-1:].isdigit() else code


def merge_tickers(batches: Sequence[Sequence[IssuerTicker]]) -> list[IssuerTicker]:
    best: dict[str, IssuerTicker] = {}
    for batch in batches:
        for item in batch:
            current = best.get(item.ticker)
            if current is None or (item.reference_date or date.min) >= (
                current.reference_date or date.min
            ):
                best[item.ticker] = item
    return list(best.values())


@dataclass(frozen=True)
class SyncResult:
    companies: int
    mapped: int
    unmapped: list[str] = field(default_factory=list)
    years: list[int] = field(default_factory=list)
    documents: int = 0
    new: int = 0
    tickers_in_map: int = 0

    def as_details(self) -> dict[str, object]:
        return {
            "companies": self.companies,
            "mapped": self.mapped,
            "unmapped": self.unmapped[:MAX_LISTED_UNMAPPED],
            "years": self.years,
            "documents": self.documents,
            "new": self.new,
            "tickers_in_map": self.tickers_in_map,
        }


def sync_documents(
    uow_factory: UoWFactory,
    *,
    fetch_tickers: Callable[[int], list[IssuerTicker]],
    fetch_documents: Callable[[int], list[CvmDocument]],
    today: date | None = None,
    now: datetime | None = None,
) -> SyncResult:
    day = today or date.today()
    seen_at = now or datetime.now(UTC)

    merged = merge_tickers([fetch_tickers(day.year - i) for i in range(FCA_YEARS)])
    with uow_factory() as uow:
        stored = uow.cvm_issuers.replace_all(merged) if merged else None
        companies = company_assets(uow.assets.list_all(active_only=True))
        tickers = sorted({base_ticker(a.ticker) for a in companies})
        cnpjs = uow.cvm_issuers.cnpjs_for(tickers)
        first_run = uow.cvm_documents.latest_delivery() is None
        uow.commit()

    years = [day.year]
    if first_run or day.month == 1:
        years.append(day.year - 1)
    wanted = set(cnpjs.values())
    found: list[CvmDocument] = []
    if wanted:
        for year in years:
            found.extend(d for d in fetch_documents(year) if d.cnpj in wanted)
    new = 0
    if found:
        with uow_factory() as uow:
            new = uow.cvm_documents.upsert_many(found, seen_at=seen_at)
            uow.commit()
    return SyncResult(
        companies=len(tickers),
        mapped=len(cnpjs),
        unmapped=[t for t in tickers if t not in cnpjs],
        years=years,
        documents=len(found),
        new=new,
        tickers_in_map=stored if stored is not None else 0,
    )
