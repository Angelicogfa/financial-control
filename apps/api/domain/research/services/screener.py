"""Screener over the B3 instrument catalog (item 11.7).

Catalog-only criteria (type, ARCA class, sector, text, liquidity, size) filter first, in
catalog order (highest financial volume first). Fundamental criteria (P/L, P/VP, DY, ROE)
then need indicators, which are fetched for at most `scan_limit` candidates so a single
request never fans out over the whole exchange.

Results are paged: `offset` skips the matches of earlier pages and `limit` is the page size.
A catalog-only search pages over every candidate and loads indicators only for the page.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from domain.assets.services.valuation import AssetValuation, value_asset
from domain.market.entities import Fundamentals
from domain.policy.services.policy import ValuationPolicy
from domain.shared.entities import AssetEntity, CatalogInstrument
from domain.shared.enums import (
    ArcaClass,
    AssetLifecycle,
    AssetType,
    default_arca_class,
    default_checklist_profile,
)

DEFAULT_LIMIT = 30
DEFAULT_SCAN_LIMIT = 120

FundamentalsLoader = Callable[[list[CatalogInstrument]], Mapping[str, Fundamentals]]


@dataclass(frozen=True)
class ScreenerCriteria:
    asset_types: frozenset[AssetType] = frozenset()
    arca_classes: frozenset[ArcaClass] = frozenset()
    sectors: frozenset[str] = frozenset()
    query: str | None = None
    min_volume_brl: float | None = None
    min_market_cap: float | None = None
    max_pe: float | None = None
    max_pb: float | None = None
    min_dy: float | None = None
    min_roe: float | None = None
    exclude_registered: bool = False
    limit: int = DEFAULT_LIMIT
    offset: int = 0
    scan_limit: int = DEFAULT_SCAN_LIMIT

    @property
    def needs_fundamentals(self) -> bool:
        return any(v is not None for v in (self.max_pe, self.max_pb, self.min_dy, self.min_roe))


@dataclass(frozen=True)
class ScreenerResult:
    instrument: CatalogInstrument
    fundamentals: Fundamentals | None = None
    valuation: AssetValuation | None = None
    asset_id: int | None = None
    lifecycle_status: AssetLifecycle | None = None


@dataclass(frozen=True)
class ScreenerOutcome:
    results: list[ScreenerResult]
    candidates: int
    scanned: int
    truncated: bool = False
    # Matches across all pages (the page itself is `results`).
    matched: int = 0
    criteria: ScreenerCriteria = field(default_factory=ScreenerCriteria)


def _matches_catalog(
    item: CatalogInstrument, c: ScreenerCriteria, registered: Mapping[str, AssetEntity]
) -> bool:
    if item.asset_type is None:
        return False
    if c.asset_types and item.asset_type not in c.asset_types:
        return False
    if c.arca_classes and default_arca_class(item.asset_type) not in c.arca_classes:
        return False
    if c.sectors and (item.sector or "").casefold() not in {s.casefold() for s in c.sectors}:
        return False
    if c.query:
        needle = c.query.strip().casefold()
        if needle not in item.ticker.casefold() and needle not in item.name.casefold():
            return False
    if c.min_volume_brl is not None and (item.volume_brl or 0.0) < c.min_volume_brl:
        return False
    if c.min_market_cap is not None and (item.market_cap or 0.0) < c.min_market_cap:
        return False
    return not (c.exclude_registered and item.ticker in registered)


def prefilter(
    catalog: Iterable[CatalogInstrument],
    criteria: ScreenerCriteria,
    registered: Mapping[str, AssetEntity] | None = None,
) -> list[CatalogInstrument]:
    """Catalog entries meeting the catalog-only criteria, in catalog order."""
    known = registered or {}
    return [item for item in catalog if _matches_catalog(item, criteria, known)]


def catalog_sectors(catalog: Iterable[CatalogInstrument]) -> list[str]:
    """Distinct sectors of the screenable catalog, alphabetical and case-insensitively unique."""
    seen: dict[str, str] = {}
    for item in catalog:
        sector = (item.sector or "").strip()
        if item.asset_type is not None and sector:
            seen.setdefault(sector.casefold(), sector)
    return sorted(seen.values(), key=str.casefold)


def passes_fundamentals(f: Fundamentals | None, c: ScreenerCriteria) -> bool:
    """Fundamental criteria; a missing indicator fails the criterion that needs it."""
    if not c.needs_fundamentals:
        return True
    if f is None:
        return False
    checks = (
        (c.max_pe, f.price_to_earnings, lambda v, t: 0 < v <= t),
        (c.max_pb, f.price_to_book, lambda v, t: 0 < v <= t),
        (c.min_dy, f.dividend_yield, lambda v, t: v >= t),
        (c.min_roe, f.return_on_equity, lambda v, t: v >= t),
    )
    for threshold, value, ok in checks:
        if threshold is None:
            continue
        if value is None or not ok(value, threshold):
            return False
    return True


def screen(
    catalog: Iterable[CatalogInstrument],
    criteria: ScreenerCriteria,
    *,
    load_fundamentals: FundamentalsLoader,
    registered: Mapping[str, AssetEntity] | None = None,
    lifecycles: Mapping[str, AssetLifecycle] | None = None,
    valuation_policy: ValuationPolicy | None = None,
) -> ScreenerOutcome:
    """Run the screener and return one page of the matches.

    Without fundamental criteria every candidate matches, so the page is cut from the
    candidates and indicators are loaded for that page only. With them, the scanned window is
    filtered first and the page is cut from what passed.
    """
    known = registered or {}
    candidates = prefilter(catalog, criteria, known)
    end = criteria.offset + criteria.limit
    if criteria.needs_fundamentals:
        scanned = candidates[: criteria.scan_limit]
        fundamentals = load_fundamentals(scanned) if scanned else {}
        matches = [
            item for item in scanned if passes_fundamentals(fundamentals.get(item.ticker), criteria)
        ]
        page = matches[criteria.offset : end]
        matched = len(matches)
    else:
        page = candidates[criteria.offset : end]
        fundamentals = load_fundamentals(page) if page else {}
        scanned = page
        matched = len(candidates)

    results: list[ScreenerResult] = []
    for item in page:
        fund = fundamentals.get(item.ticker)
        asset = known.get(item.ticker)
        profile = asset.profile if asset else default_checklist_profile(item.asset_type)  # type: ignore[arg-type]
        results.append(
            ScreenerResult(
                instrument=item,
                fundamentals=fund,
                valuation=value_asset(profile, item.close, fund, valuation_policy),
                asset_id=asset.id if asset else None,
                lifecycle_status=(lifecycles or {}).get(item.ticker),
            )
        )
    return ScreenerOutcome(
        results=results,
        candidates=len(candidates),
        scanned=len(scanned),
        truncated=criteria.needs_fundamentals and len(candidates) > criteria.scan_limit,
        criteria=criteria,
        matched=matched,
    )
