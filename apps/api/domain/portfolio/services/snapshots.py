"""Daily portfolio snapshot helpers: external flows, snapshot building and history windows."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Sequence
from datetime import date, timedelta

from domain.portfolio.services.consolidation import LEDGER_VALID, ConsolidatedPortfolioReport
from domain.shared.entities import AssetEntity, PortfolioSnapshotEntity, TransactionEntity
from domain.shared.enums import TransactionKind
from domain.shared.unit_of_work import AbstractUnitOfWork

MAX_HISTORY_YEARS = 10


def invalidate_snapshots_from(uow: AbstractUnitOfWork, *changed: date | None) -> int:
    """Drop every snapshot dated on or after the earliest changed ledger date.

    Snapshots are derived from the ledger, so a backdated (or edited/removed) entry makes
    the stored ones stale; the worker backfill recreates the deleted days.
    """
    dates = [d for d in changed if d is not None]
    if not dates:
        return 0
    return uow.snapshots.delete_range(date_from=min(dates))


def external_flow_brl(tx: TransactionEntity) -> float:
    """Cash entering (+) or leaving (-) the portfolio because of a trade, in BRL."""
    gross = float(tx.quantity * tx.unit_price)
    fees = float(tx.fees)
    fx = float(tx.fx_rate)
    if tx.kind == TransactionKind.BUY:
        return (gross + fees) * fx
    return -(gross - fees) * fx


def net_flow_between(assets: Iterable[AssetEntity], after: date | None, up_to: date) -> float:
    """Net external flow of every trade dated in (after, up_to] (finding I-09)."""
    return round(
        sum(
            external_flow_brl(tx)
            for asset in assets
            for tx in asset.transactions
            if tx.trade_date <= up_to and (after is None or tx.trade_date > after)
        ),
        2,
    )


def first_trade_date(assets: Iterable[AssetEntity]) -> date | None:
    dates = [tx.trade_date for asset in assets for tx in asset.transactions]
    return min(dates) if dates else None


def snapshot_from_report(
    report: ConsolidatedPortfolioReport, *, net_flow: float
) -> PortfolioSnapshotEntity:
    """Persistable snapshot of a consolidated report."""
    return PortfolioSnapshotEntity(
        snapshot_date=report.as_of_date,
        invested_value=report.total_invested_brl,
        market_value=report.total_current_value_brl,
        unrealized_pnl=report.total_unrealized_pnl_brl,
        realized_pnl_cum=report.total_realized_pnl_brl,
        earnings_cum=report.total_received_earnings_brl,
        consolidated_pnl=report.total_consolidated_pnl_brl,
        net_flow=net_flow,
        by_class={
            alloc.arca_class.value: {
                "invested_value": alloc.invested_value,
                "current_value": alloc.current_value,
                "current_pct": alloc.current_pct,
                "target_pct": alloc.target_pct,
            }
            for alloc in report.allocations
        },
    )


def invalid_ledger_tickers(report: ConsolidatedPortfolioReport) -> list[str]:
    return [p.ticker for p in report.positions if p.ledger_status != LEDGER_VALID]


def history_range_for(start: date, end: date) -> str:
    """Smallest provider range keyword (brapi/yfinance) covering [start, end]."""
    years = (end - start).days / 365.0
    for limit, keyword in ((1, "1y"), (2, "2y"), (5, "5y"), (10, "10y")):
        if years <= limit:
            return keyword
    return "max"


def history_start(end: date, *candidates: date | None) -> date:
    """Earliest needed date among candidates, never further than MAX_HISTORY_YEARS back."""
    floor = end - timedelta(days=365 * MAX_HISTORY_YEARS)
    default = end - timedelta(days=365)
    wanted = min([d for d in candidates if d is not None] + [default])
    return max(wanted, floor)


class PriceLookup:
    """Last known close on or before a date (prices are carried over non-trading days)."""

    def __init__(self, points: Sequence[tuple[date, float]]) -> None:
        ordered = sorted(points)
        self._dates = [d for d, _ in ordered]
        self._values = [v for _, v in ordered]

    def __bool__(self) -> bool:
        return bool(self._dates)

    def on(self, day: date) -> float | None:
        index = bisect_right(self._dates, day)
        return self._values[index - 1] if index else None
