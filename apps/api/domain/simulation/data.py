"""Simulation data (Phase 33.1): stored series, coverage report and the point-in-time history.

Series live in `market_series` under their own symbols, so the simulation never touches the
series the portfolio screens read:
- `SIM:TR:<TICKER>` total return (Yahoo "Adj Close": splits and dividends), in the trading
  currency, unit PRICE;
- `SIM:PX:<TICKER>` close adjusted only for splits (lot sizes), unit PRICE;
- `SIM:IDX:<LABEL>` long index history (IBOV and S&P 500 total return), unit INDEX_POINTS;
- `SIM:FX:USDBRL` dollar in reais, unit PRICE.
CDI and IPCA reuse the BCB series (`CDI`, `IPCA`). IFIX has no long history on Yahoo: the
stored `IFIX` benchmark (up to ten years) is used, and the coverage report shows the limit.

`build_market_history` reads only the database, so a simulation never calls the internet.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

from core.helpers.units import daily_rates, monthly_rates
from domain.market.services.price_sanity import price_spikes
from domain.shared.entities import AssetEntity
from domain.shared.enums import Market
from domain.shared.repositories import AbstractMarketSeriesRepository
from domain.shared.unit_of_work import AbstractUnitOfWork
from domain.simulation.market import MarketHistory, PriceSeries, accumulate_rate_index

TR_PREFIX = "SIM:TR:"
PX_PREFIX = "SIM:PX:"
IDX_PREFIX = "SIM:IDX:"
SPLIT_PREFIX = "SIM:SPLIT:"
FX_USDBRL = "SIM:FX:USDBRL"

# Long index series loaded from Yahoo: label -> Yahoo symbol.
INDEX_SOURCES: dict[str, str] = {"IBOV": "^BVSP", "SP500TR": "^SP500TR"}
# Series names the engine reads (MarketHistory keys).
CDI_KEY = "CDI"
IBOV_KEY = "IBOV"
IFIX_KEY = "IFIX"
SP500_BRL_KEY = "SP500_BRL"

SIMULATION_HISTORY_START = date(2005, 1, 3)
# Coverage below this share of the expected months counts as partial.
MIN_COVERAGE = 0.95
MAX_GAP_DAYS = 10  # trading gaps longer than this (calendar days) are reported
# A gap above this breaks the coverage (monthly series such as IPCA reach ~33 days).
MAX_OK_GAP_DAYS = 45


def tr_symbol(ticker: str) -> str:
    return f"{TR_PREFIX}{ticker.strip().upper()}"


def px_symbol(ticker: str) -> str:
    return f"{PX_PREFIX}{ticker.strip().upper()}"


def split_symbol(ticker: str) -> str:
    """Splits and bonus issues of a ticker (shares after / before), from Yahoo (Phase 42.3)."""
    return f"{SPLIT_PREFIX}{ticker.strip().upper()}"


def index_symbol(label: str) -> str:
    return f"{IDX_PREFIX}{label}"


class CoverageStatus(StrEnum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


@dataclass(frozen=True)
class SeriesCoverage:
    """How much of [start, end] a stored series covers."""

    key: str
    label: str
    status: CoverageStatus
    first_date: date | None = None
    last_date: date | None = None
    points: int = 0
    months_expected: int = 0
    months_covered: int = 0
    longest_gap_days: int = 0
    note: str | None = None

    @property
    def share(self) -> float:
        return self.months_covered / self.months_expected if self.months_expected else 0.0


@dataclass(frozen=True)
class CoverageReport:
    start: date
    end: date
    series: list[SeriesCoverage] = field(default_factory=list)

    @property
    def missing(self) -> list[str]:
        return [s.key for s in self.series if s.status == CoverageStatus.MISSING]


def _months(start: date, end: date) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        out.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def series_coverage(
    key: str, label: str, dates: Sequence[date], start: date, end: date
) -> SeriesCoverage:
    """Months of [start, end] with at least one point, first/last date and the longest gap."""
    inside = sorted(d for d in dates if start <= d <= end)
    expected = _months(start, end)
    if not inside:
        return SeriesCoverage(
            key,
            label,
            CoverageStatus.MISSING,
            months_expected=len(expected),
            note="Sem pontos no período.",
        )
    covered = {(d.year, d.month) for d in inside}
    gap = max(((b - a).days for a, b in zip(inside[:-1], inside[1:], strict=False)), default=0)
    months_covered = sum(1 for m in expected if m in covered)
    share = months_covered / len(expected) if expected else 0.0
    status = (
        CoverageStatus.OK
        if share >= MIN_COVERAGE and gap <= MAX_OK_GAP_DAYS
        else CoverageStatus.PARTIAL
    )
    notes = []
    if inside[0] - start > timedelta(days=31):
        notes.append(f"Começa em {inside[0].strftime('%d/%m/%Y')}.")
    if gap > MAX_GAP_DAYS:
        notes.append(f"Maior intervalo sem dados: {gap} dias.")
    return SeriesCoverage(
        key=key,
        label=label,
        status=status,
        first_date=inside[0],
        last_date=inside[-1],
        points=len(inside),
        months_expected=len(expected),
        months_covered=months_covered,
        longest_gap_days=gap,
        note=" ".join(notes) or None,
    )


def coverage_report(
    series: AbstractMarketSeriesRepository,
    tickers: Sequence[str],
    *,
    start: date,
    end: date,
) -> CoverageReport:
    """Coverage of every series a simulation over `tickers` would read."""
    wanted: list[tuple[str, str, str]] = [
        (CDI_KEY, "CDI", CDI_KEY),
        ("IPCA", "IPCA", "IPCA"),
        (IBOV_KEY, "Ibovespa (retorno total)", index_symbol("IBOV")),
        (IFIX_KEY, "IFIX", "IFIX"),
        ("SP500TR", "S&P 500 (retorno total, US$)", index_symbol("SP500TR")),
        ("USDBRL", "Dólar (R$)", FX_USDBRL),
        *((t.upper(), t.upper(), tr_symbol(t)) for t in tickers),
    ]
    return CoverageReport(
        start=start,
        end=end,
        series=[
            series_coverage(
                key,
                label,
                [
                    p.reference_date
                    for p in series.list_series(symbol, date_from=start, date_to=end)
                ],
                start,
                end,
            )
            for key, label, symbol in wanted
        ],
    )


def _price_series(points: Sequence[tuple[date, float]]) -> PriceSeries:
    """The stored series without isolated bad prints of the provider (Phase 32.4)."""
    ordered = sorted((d, p) for d, p in points if p is not None and p > 0)
    keep, _ = price_spikes([d for d, _ in ordered], [p for _, p in ordered])
    return PriceSeries.from_points([pt for pt, ok in zip(ordered, keep, strict=True) if ok])


def _in_brl(points: Sequence[tuple[date, float]], usd_brl: PriceSeries) -> list[tuple[date, float]]:
    """Convert a USD series with the dollar of each day (last known rate)."""
    out: list[tuple[date, float]] = []
    for day, value in points:
        rate = usd_brl.last_on_or_before(day)
        if rate:
            out.append((day, value * rate))
    return out


def build_market_history(
    series: AbstractMarketSeriesRepository,
    tickers: Sequence[str],
    *,
    start: date,
    end: date,
    currency_by_ticker: Mapping[str, str] | None = None,
) -> MarketHistory:
    """Point-in-time history from the database only (assets, indices, CDI index, IPCA).

    Asset series come in reais: USD assets are converted with the dollar of each day. Keys
    are the tickers plus `CDI`, `IBOV`, `IFIX` and `SP500_BRL`.
    """
    currencies = {k.upper(): v.upper() for k, v in (currency_by_ticker or {}).items()}

    def points(symbol: str) -> list[tuple[date, float]]:
        return [
            (p.reference_date, p.value)
            for p in series.list_series(symbol, date_from=start, date_to=end)
        ]

    usd_brl = _price_series(points(FX_USDBRL))
    out: dict[str, PriceSeries] = {}
    for ticker in tickers:
        key = ticker.upper()
        raw = points(tr_symbol(key))
        if currencies.get(key, "BRL") == "USD":
            raw = _in_brl(raw, usd_brl)
        if raw:
            out[key] = _price_series(raw)
    ibov = points(index_symbol("IBOV")) or points("IBOV")
    if ibov:
        out[IBOV_KEY] = _price_series(ibov)
    ifix = points("IFIX")
    if ifix:
        out[IFIX_KEY] = _price_series(ifix)
    sp500 = _in_brl(points(index_symbol("SP500TR")), usd_brl)
    if sp500:
        out[SP500_BRL_KEY] = _price_series(sp500)
    cdi = daily_rates(series.list_series(CDI_KEY, date_from=start, date_to=end))
    if cdi:
        # accumulate_rate_index takes % a day; daily_rates already checked the unit.
        out[CDI_KEY] = accumulate_rate_index([(d, r * 100.0) for d, r in sorted(cdi.items())])
    ipca = series.list_series("IPCA", date_from=date(start.year, start.month, 1), date_to=end)
    return MarketHistory(series=out, ipca_monthly=monthly_rates(ipca))


def simulation_universe(uow: AbstractUnitOfWork, catalog_top: int) -> list[AssetEntity]:
    """Market-traded assets held or followed, plus the most traded catalog instruments."""
    assets = [
        a
        for a in uow.assets.list_all(active_only=True)
        if a.market not in (Market.MANUAL, Market.FIXED_INCOME_CURVE)
    ]
    known = {a.ticker for a in assets}
    if catalog_top > 0:
        ranked = sorted(
            (
                i
                for i in uow.catalog.list_all()
                if i.asset_type is not None and i.ticker not in known
            ),
            key=lambda i: -(i.volume_brl or 0.0),
        )
        for item in ranked[:catalog_top]:
            assets.append(
                AssetEntity(ticker=item.ticker, name=item.name, asset_type=item.asset_type)  # type: ignore[arg-type]
            )
    return assets
