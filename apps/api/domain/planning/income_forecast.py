"""Future passive income (Phase 48.R8, Planejar › Renda futura). Pure.

Two parts, never added twice:
- **declared**: the distributions already announced for the assets held (earnings agenda);
- **estimated**: each earning received in the last 12 months returns in the same calendar
  month, per unit, at the quantity held today (FIIs monthly, companies by their own calendar).
  An asset-month with a declared amount is not estimated again.
No growth is assumed; it is the income of the portfolio as it is now.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from domain.portfolio.services.income import net_brl
from domain.portfolio.services.positions import InsufficientQuantityError, build_position
from domain.shared.entities import AssetEntity

ZERO = Decimal("0")


@dataclass(frozen=True)
class DeclaredIncome:
    asset_id: int
    ticker: str
    payment_date: date
    net_brl: float


@dataclass(frozen=True)
class ForecastMonth:
    month: str  # YYYY-MM
    declared_brl: float
    estimated_brl: float

    @property
    def total_brl(self) -> float:
        return round(self.declared_brl + self.estimated_brl, 2)


@dataclass(frozen=True)
class AssetForecast:
    asset_id: int
    ticker: str
    next_12m_brl: float


@dataclass(frozen=True)
class IncomeForecast:
    as_of: date
    months: list[ForecastMonth]
    next_12m_brl: float
    declared_brl: float
    assets: list[AssetForecast] = field(default_factory=list)


def _month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def _add_months(d: date, months: int) -> date:
    total = d.year * 12 + d.month - 1 + months
    return date(total // 12, total % 12 + 1, 1)


def _quantity(asset: AssetEntity, on: date) -> Decimal:
    try:
        return build_position(
            asset.transactions, up_to_date=on, events=asset.corporate_events
        ).quantity
    except InsufficientQuantityError:
        return ZERO


def forecast_income(
    assets: Iterable[AssetEntity],
    declared: Iterable[DeclaredIncome],
    *,
    today: date,
    months: int = 12,
) -> IncomeForecast:
    start = today.replace(day=1)
    keys = [_month_key(_add_months(start, i)) for i in range(months)]
    declared_by: dict[tuple[int, str], float] = defaultdict(float)
    for d in declared:
        if d.payment_date >= today:
            declared_by[(d.asset_id, _month_key(d.payment_date))] += d.net_brl
    estimated_by: dict[tuple[int, str], float] = defaultdict(float)
    tickers: dict[int, str] = {}
    year_ago = date(today.year - 1, today.month, 1)
    for asset in assets:
        if asset.id is None:
            continue
        tickers[asset.id] = asset.ticker
        now = _quantity(asset, today)
        if now <= ZERO:
            continue
        for e in asset.earnings:
            if not (year_ago <= e.payment_date < start):
                continue
            held = _quantity(asset, e.ex_date or e.payment_date)
            if held <= ZERO:
                continue
            per_unit = net_brl(e) / held
            for key in keys:
                if key[5:] == e.payment_date.strftime("%m"):
                    estimated_by[(asset.id, key)] += float(per_unit * now)
    for d in declared:
        tickers.setdefault(d.asset_id, d.ticker)
    out_months = []
    for key in keys:
        dec = sum(v for (a, k), v in declared_by.items() if k == key)
        est = sum(v for (a, k), v in estimated_by.items() if k == key and (a, k) not in declared_by)
        out_months.append(ForecastMonth(key, round(dec, 2), round(est, 2)))
    first_year = set(keys[:12])
    per_asset: dict[int, float] = defaultdict(float)
    for (a, k), v in declared_by.items():
        if k in first_year:
            per_asset[a] += v
    for (a, k), v in estimated_by.items():
        if k in first_year and (a, k) not in declared_by:
            per_asset[a] += v
    return IncomeForecast(
        as_of=today,
        months=out_months,
        next_12m_brl=round(sum(m.total_brl for m in out_months[:12]), 2),
        declared_brl=round(sum(m.declared_brl for m in out_months), 2),
        assets=sorted(
            (
                AssetForecast(a, tickers.get(a, str(a)), round(v, 2))
                for a, v in per_asset.items()
                if v > 0
            ),
            key=lambda x: -x.next_12m_brl,
        ),
    )
