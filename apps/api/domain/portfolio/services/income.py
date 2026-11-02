"""Earnings received, by month and year (Phase 48.R5, Carteira › Proventos).

Net of withholding, in BRL (the payment's FX rate), straight from the ledger. The yield on
cost divides the last 12 months by what is invested now in the assets that paid them.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from domain.portfolio.services.positions import InsufficientQuantityError, build_position
from domain.shared.entities import AssetEntity, EarningEntity
from domain.shared.unit_of_work import UoWFactory

ZERO = Decimal("0")


@dataclass(frozen=True)
class MonthIncome:
    month: str  # YYYY-MM
    net_brl: float


@dataclass(frozen=True)
class AssetIncome:
    asset_id: int
    ticker: str
    last_12m_brl: float
    yield_on_cost: float | None  # last 12 months over the cost of the position now


@dataclass(frozen=True)
class IncomeSummary:
    as_of: date
    last_12m_brl: float
    previous_12m_brl: float
    total_brl: float
    yield_on_cost: float | None
    months: list[MonthIncome] = field(default_factory=list)  # oldest first
    by_year: dict[int, float] = field(default_factory=dict)
    assets: list[AssetIncome] = field(default_factory=list)  # best paying first


def net_brl(earning: EarningEntity) -> Decimal:
    net = (
        earning.net_amount
        if earning.net_amount is not None
        else earning.gross_amount - earning.withholding_tax
    )
    return net * earning.fx_rate


def _months_back(day: date, months: int) -> date:
    total = day.year * 12 + day.month - 1 - months
    return date(total // 12, total % 12 + 1, 1)


def _cost(asset: AssetEntity, on: date) -> Decimal:
    try:
        return build_position(
            asset.transactions, up_to_date=on, events=asset.corporate_events
        ).total_cost_brl
    except InsufficientQuantityError:
        return ZERO


def summarize(assets: list[AssetEntity], today: date, months: int = 24) -> IncomeSummary:
    year_ago = _months_back(today.replace(day=1), 11)
    two_years_ago = _months_back(today.replace(day=1), 23)
    monthly: dict[str, Decimal] = defaultdict(lambda: ZERO)
    yearly: dict[int, Decimal] = defaultdict(lambda: ZERO)
    last, previous, total, invested = ZERO, ZERO, ZERO, ZERO
    per_asset: list[AssetIncome] = []
    for asset in assets:
        recent = ZERO
        for e in asset.earnings:
            if e.payment_date > today:
                continue
            value = net_brl(e)
            total += value
            yearly[e.payment_date.year] += value
            monthly[e.payment_date.strftime("%Y-%m")] += value
            if e.payment_date >= year_ago:
                recent += value
            elif e.payment_date >= two_years_ago:
                previous += value
        if recent > ZERO and asset.id is not None:
            cost = _cost(asset, today)
            invested += cost
            last += recent
            per_asset.append(
                AssetIncome(
                    asset_id=asset.id,
                    ticker=asset.ticker,
                    last_12m_brl=round(float(recent), 2),
                    yield_on_cost=round(float(recent / cost), 4) if cost > ZERO else None,
                )
            )
    start = _months_back(today.replace(day=1), months - 1)
    keys = [
        _months_back(today.replace(day=1), i).strftime("%Y-%m") for i in range(months - 1, -1, -1)
    ]
    return IncomeSummary(
        as_of=today,
        last_12m_brl=round(float(last), 2),
        previous_12m_brl=round(float(previous), 2),
        total_brl=round(float(total), 2),
        yield_on_cost=round(float(last / invested), 4) if invested > ZERO else None,
        months=[
            MonthIncome(k, round(float(monthly.get(k, ZERO)), 2))
            for k in keys
            if k >= start.strftime("%Y-%m")
        ],
        by_year={y: round(float(v), 2) for y, v in sorted(yearly.items())},
        assets=sorted(per_asset, key=lambda a: -a.last_12m_brl),
    )


class IncomeHandler:
    """`GET /portfolio/income`: what the portfolio paid, month by month."""

    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def summary(self, *, months: int = 24, today: date | None = None) -> IncomeSummary:
        with self.uow_factory() as uow:
            assets = uow.assets.list_all(active_only=False)
        return summarize(assets, today or date.today(), months)
