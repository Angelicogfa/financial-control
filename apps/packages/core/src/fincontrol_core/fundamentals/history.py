"""Yearly financial statement history and the multi-year metrics derived from it (11.1, 11.2).

Point-in-time indicators (TTM ROE, current DY) cannot answer questions such as "ROE
historically above 5%?" or "pays dividends consistently?" (finding F-02). Annual snapshots
let the checklist answer them with evidence.

Monetary values are in the instrument's reporting currency; ratios are fractions (ADR 0006).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from fincontrol_core.domain.enums import AssetType

DEFAULT_WINDOW_YEARS = 5

# Asset types whose issuers publish income statements and balance sheets.
STATEMENT_TYPES = frozenset({AssetType.STOCK_BR, AssetType.STOCK_INTL, AssetType.BDR})


class FundamentalPeriod(StrEnum):
    ANNUAL = "ANNUAL"
    TTM = "TTM"


# Keys stored in `FundamentalSnapshot.metrics`.
METRIC_KEYS: tuple[str, ...] = (
    "revenue",
    "net_income",
    "ebitda",
    "equity",
    "total_debt",
    "cash",
    "dividends_paid",
)


@dataclass(frozen=True)
class FundamentalSnapshot:
    """Statement figures for one fiscal year (ANNUAL) or the trailing twelve months (TTM)."""

    ticker: str
    reference_date: date
    period: FundamentalPeriod
    metrics: Mapping[str, float | None] = field(default_factory=dict)
    source: str | None = None
    id: int | None = None

    def value(self, key: str) -> float | None:
        return self.metrics.get(key)


@dataclass(frozen=True)
class HistoricalMetrics:
    """Multi-year view of a company's fundamentals over `years` fiscal years."""

    years: int
    first_year: int | None
    last_year: int | None
    roe_average: float | None
    revenue_cagr: float | None
    earnings_cagr: float | None
    profitable_years: int
    dividend_years: int
    payout_average: float | None

    @property
    def always_profitable(self) -> bool:
        return self.years > 0 and self.profitable_years == self.years

    @property
    def dividend_regularity(self) -> float | None:
        return self.dividend_years / self.years if self.years else None


def _cagr(first: float | None, last: float | None, periods: int) -> float | None:
    if first is None or last is None or periods <= 0 or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1.0 / periods) - 1.0


def _average(values: Iterable[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if known else None


def historical_metrics(
    snapshots: Iterable[FundamentalSnapshot], *, window_years: int = DEFAULT_WINDOW_YEARS
) -> HistoricalMetrics:
    """Derive ROE average, revenue/earnings CAGR, profit and dividend regularity, payout."""
    annual = sorted(
        (s for s in snapshots if s.period == FundamentalPeriod.ANNUAL),
        key=lambda s: s.reference_date,
    )[-window_years:]
    if not annual:
        return HistoricalMetrics(0, None, None, None, None, None, 0, 0, None)

    def ratio(numerator: float | None, denominator: float | None) -> float | None:
        if numerator is None or denominator is None or denominator <= 0:
            return None
        return numerator / denominator

    periods = len(annual) - 1
    first, last = annual[0], annual[-1]
    net_incomes = [s.value("net_income") for s in annual]
    dividends = [s.value("dividends_paid") for s in annual]
    return HistoricalMetrics(
        years=len(annual),
        first_year=first.reference_date.year,
        last_year=last.reference_date.year,
        roe_average=_average(ratio(s.value("net_income"), s.value("equity")) for s in annual),
        revenue_cagr=_cagr(first.value("revenue"), last.value("revenue"), periods),
        earnings_cagr=_cagr(first.value("net_income"), last.value("net_income"), periods),
        profitable_years=sum(1 for v in net_incomes if v is not None and v > 0),
        dividend_years=sum(1 for v in dividends if v is not None and abs(v) > 0),
        payout_average=_average(
            ratio(abs(d) if d is not None else None, n)
            for d, n in zip(dividends, net_incomes, strict=True)
        ),
    )


def snapshot_to_dict(snapshot: FundamentalSnapshot) -> dict[str, object]:
    return {
        "ticker": snapshot.ticker,
        "reference_date": snapshot.reference_date.isoformat(),
        "period": snapshot.period.value,
        "metrics": dict(snapshot.metrics),
        "source": snapshot.source,
    }


def snapshot_from_dict(data: Mapping[str, object]) -> FundamentalSnapshot:
    return FundamentalSnapshot(
        ticker=str(data["ticker"]),
        reference_date=date.fromisoformat(str(data["reference_date"])),
        period=FundamentalPeriod(str(data["period"])),
        metrics=dict(data.get("metrics") or {}),  # type: ignore[call-overload]
        source=data.get("source"),  # type: ignore[arg-type]
    )
