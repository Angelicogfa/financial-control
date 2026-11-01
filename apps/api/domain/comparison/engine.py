"""The engine of the live scoreboard (design 36, section 3): the real flow, applied by a strategy.

On every valuation day (month ends plus the days with ARCA trades) the engine:
1. grows the uninvested cash by the CDI since the previous day;
2. on a day with money in, invests the cash by deficit: each asset gets the cash in proportion
   to how far it is below its target (class share x weight in the class), in whole lots on the
   B3 with the trading fees; what the lots leave over stays in cash, earning the CDI;
3. on a day with money out, takes the cash first and sells the rest in proportion to the
   holdings, paying the income tax of the asset type (Brazilian stocks exempt up to R$ 20 mil
   of sales in the month);
4. records the value of the portfolio.

There are no other sales: like the real contribution, it moves toward the targets only with
new money (decision 10.1.8). Prices are total-return series in BRL, so the earnings are
reinvested in the asset that paid them (like the simulation, risk R7). The state of the book is
kept between runs, so the daily routine only adds the new days.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from domain.comparison.flow import ActualTrade
from domain.comparison.points import Point
from domain.comparison.strategies import Strategy
from domain.shared.enums import INTEGER_QUANTITY_TYPES, ArcaClass, AssetType
from domain.simulation.data import CDI_KEY
from domain.simulation.engine import STOCK_MONTHLY_EXEMPTION_BRL, sale_tax_rate
from domain.simulation.market import MarketHistory, PointInTimeView, PriceSeries, month_ends
from domain.tax.entities import TaxRuleBook
from domain.tax.services.rules import DEFAULT_RULE_BOOK

FEE_RATE = 0.0003  # B3 trading fees (emolumentos)
MIN_CENTS = 0.01
DEFAULT_TYPE = AssetType.ETF_BR  # the class indices are held as their index ETFs
TYPE_OF_CASH = AssetType.TREASURY  # the CDI as Tesouro Selic


@dataclass
class Book:
    """What a comparison portfolio holds: units of each series, cost, cash and the totals."""

    units: dict[str, float] = field(default_factory=dict)
    cost: dict[str, float] = field(default_factory=dict)
    first_buy: dict[str, date] = field(default_factory=dict)
    cash: float = 0.0
    contributed: float = 0.0
    fees: float = 0.0
    taxes: float = 0.0
    trades: int = 0
    day: date | None = None
    stock_sales: dict[str, float] = field(default_factory=dict)  # "YYYY-MM" -> BRL sold

    def value(self, view: PointInTimeView) -> float:
        return self.cash + sum(
            units * (view.price(symbol) or 0.0) for symbol, units in self.units.items()
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "units": self.units,
            "cost": self.cost,
            "first_buy": {s: d.isoformat() for s, d in self.first_buy.items()},
            "cash": self.cash,
            "contributed": self.contributed,
            "fees": self.fees,
            "taxes": self.taxes,
            "trades": self.trades,
            "day": self.day.isoformat() if self.day else None,
            "stock_sales": self.stock_sales,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Book:
        return cls(
            units={k: float(v) for k, v in data.get("units", {}).items()},
            cost={k: float(v) for k, v in data.get("cost", {}).items()},
            first_buy={k: date.fromisoformat(v) for k, v in data.get("first_buy", {}).items()},
            cash=float(data.get("cash", 0.0)),
            contributed=float(data.get("contributed", 0.0)),
            fees=float(data.get("fees", 0.0)),
            taxes=float(data.get("taxes", 0.0)),
            trades=int(data.get("trades", 0)),
            day=date.fromisoformat(data["day"]) if data.get("day") else None,
            stock_sales={k: float(v) for k, v in data.get("stock_sales", {}).items()},
        )


@dataclass(frozen=True)
class Market:
    """The total-return series (valuation) and, for whole lots, the plain price series."""

    history: MarketHistory
    lot_prices: Mapping[str, PriceSeries] = field(default_factory=dict)
    asset_types: Mapping[str, AssetType] = field(default_factory=dict)
    fee_rate: float = FEE_RATE
    tax_rules: TaxRuleBook = DEFAULT_RULE_BOOK

    def asset_type(self, symbol: str) -> AssetType:
        if symbol == CDI_KEY:
            return TYPE_OF_CASH
        return self.asset_types.get(symbol, DEFAULT_TYPE)

    def lot_price(self, symbol: str, day: date) -> float | None:
        if self.asset_type(symbol) not in INTEGER_QUANTITY_TYPES:
            return None
        series = self.lot_prices.get(symbol)
        return series.last_on_or_before(day) if series else None


def valuation_days(flow_days: Sequence[date], start: date, end: date) -> list[date]:
    """Month ends plus the days with flow, between `start` and `end`."""
    days = set(month_ends(start, end))
    days.update(d for d in flow_days if start <= d <= end)
    return sorted(days)


def _grow_cash(book: Book, view: PointInTimeView) -> None:
    if book.day is None or book.cash <= 0:
        return
    now, before = view.price(CDI_KEY), view.price(CDI_KEY, book.day)
    if now and before:
        book.cash *= now / before


def _buy(book: Book, market: Market, view: PointInTimeView, symbol: str, amount: float) -> None:
    price = view.price(symbol)
    if not price or amount < MIN_CENTS:
        return
    lot = market.lot_price(symbol, view.as_of)
    if lot:
        quantity = math.floor(amount / (lot * (1.0 + market.fee_rate)))
        spend = quantity * lot
    else:
        spend = amount / (1.0 + market.fee_rate)
    if spend < MIN_CENTS:
        return
    fee = spend * market.fee_rate
    book.units[symbol] = book.units.get(symbol, 0.0) + spend / price
    book.cost[symbol] = book.cost.get(symbol, 0.0) + spend + fee
    book.first_buy.setdefault(symbol, view.as_of)
    book.cash -= spend + fee
    book.fees += fee
    book.trades += 1


def targets_of(
    holdings: Mapping[ArcaClass, Mapping[str, float]], shares: Mapping[ArcaClass, float]
) -> dict[str, float]:
    """Share of the whole portfolio of each symbol; an empty class is held in the CDI."""
    out: dict[str, float] = {}
    for arca_class, share in shares.items():
        weights = holdings.get(arca_class) or {CDI_KEY: 1.0}
        total = sum(weights.values())
        for symbol, weight in weights.items():
            out[symbol] = out.get(symbol, 0.0) + share * weight / total
    return out


def invest(book: Book, market: Market, view: PointInTimeView, targets: Mapping[str, float]) -> None:
    """Spend the cash on the assets below their target, in proportion to the gap."""
    priced = {s: w for s, w in targets.items() if view.price(s)}
    if book.cash < MIN_CENTS or not priced:
        return
    total = book.value(view)
    gaps = {
        s: max(0.0, w * total - book.units.get(s, 0.0) * (view.price(s) or 0.0))
        for s, w in priced.items()
    }
    gap = sum(gaps.values())
    if gap <= 0:
        return
    budget = book.cash
    for symbol, missing in sorted(gaps.items()):
        if missing > 0:
            _buy(book, market, view, symbol, budget * missing / gap)


def withdraw(book: Book, market: Market, view: PointInTimeView, amount: float) -> None:
    """Take `amount` out: the cash first, then sales in proportion to the holdings, with tax."""
    taken = min(book.cash, amount)
    book.cash -= taken
    need = amount - taken
    for _ in range(8):  # the tax of a sale is paid by smaller sales after it
        values = {s: u * (view.price(s) or 0.0) for s, u in book.units.items()}
        held = sum(values.values())
        if need < MIN_CENTS or held <= 0:
            break
        paid = 0.0
        month = view.as_of.strftime("%Y-%m")
        for symbol, value in values.items():
            if value <= 0:
                continue
            gross = min(value, need * value / held / (1.0 - market.fee_rate))
            fraction = gross / value
            cost = book.cost.get(symbol, 0.0) * fraction
            fee = gross * market.fee_rate
            asset_type = market.asset_type(symbol)
            tax = 0.0
            gain = gross - fee - cost
            if asset_type == AssetType.STOCK_BR:
                book.stock_sales[month] = book.stock_sales.get(month, 0.0) + gross
            exempt = (
                asset_type == AssetType.STOCK_BR
                and book.stock_sales[month] <= STOCK_MONTHLY_EXEMPTION_BRL
            )
            if gain > 0 and not exempt:
                first = book.first_buy.get(symbol, view.as_of)
                try:
                    rate = sale_tax_rate(
                        asset_type, view.as_of, (view.as_of - first).days, market.tax_rules
                    )
                except (KeyError, LookupError):
                    rate = 0.15
                tax = gain * rate
            book.units[symbol] -= book.units[symbol] * fraction
            book.cost[symbol] = book.cost.get(symbol, 0.0) - cost
            book.fees += fee
            book.taxes += tax
            book.trades += 1
            paid += gross - fee - tax
        need -= paid
    if need > MIN_CENTS:  # the flow took out more than the portfolio had
        book.cash -= need
    book.units = {s: u for s, u in book.units.items() if u > 1e-12}


def run_strategy(
    strategy: Strategy,
    market: Market,
    flows: Mapping[date, float],
    days: Sequence[date],
    policy_targets: Mapping[ArcaClass, float],
    *,
    book: Book | None = None,
    initial: float = 0.0,
) -> tuple[list[Point], Book]:
    """Apply the flow on `days` after the book's last day (see the module docstring).

    `initial` enters as money in on the first new day (the starting patrimony, decision 10.1.8).
    Days before the strategy has a decision are skipped: it starts on its first decision.
    """
    book = book or Book()
    shares = strategy.class_targets(policy_targets)
    points: list[Point] = []
    pending = initial
    for day in days:
        if book.day is not None and day <= book.day:
            continue
        view = market.history.view(day)
        holdings = strategy.decide(day, view)
        if holdings is None:
            continue
        _grow_cash(book, view)
        flow = flows.get(day, 0.0) + pending
        pending = 0.0
        if flow > 0:
            book.cash += flow
            book.contributed += flow
            invest(book, market, view, targets_of(holdings, shares))
        elif flow < 0:
            book.contributed += flow
            withdraw(book, market, view, -flow)
        book.day = day
        points.append(
            Point(
                day=day,
                flow=round(flow, 2),
                contributed=round(book.contributed, 2),
                value=round(book.value(view), 2),
                cash=round(book.cash, 2),
                fees=round(book.fees, 2),
                taxes=round(book.taxes, 2),
            )
        )
    return points, book


def replay_actual(
    trades: Sequence[ActualTrade],
    market: Market,
    days: Sequence[date],
    *,
    book: Book | None = None,
    shares: dict[str, float] | None = None,
) -> tuple[list[Point], Book, dict[str, float]]:
    """The real ARCA portfolio valued with the same series, so the comparison is fair.

    Each real trade buys or sells units of the asset's total-return series at the trade day's
    price. An asset without a series from its first trade on (fixed income, a series that starts
    later) is valued by the CDI. `shares` keeps the real quantity held, to turn a sale into a
    fraction of the units.
    """
    book = book or Book()
    shares = dict(shares or {})
    history = market.history
    first_trade: dict[str, date] = {}
    for t in trades:
        first_trade.setdefault(t.ticker, t.day)

    def symbol_of(ticker: str) -> str:
        series = history.series.get(ticker)
        first = series.first_date if series else None
        return ticker if first is not None and first <= first_trade[ticker] else CDI_KEY

    points: list[Point] = []
    previous = book.day
    for day in days:
        if previous is not None and day <= previous:
            continue
        view = history.view(day)
        flow = 0.0
        for trade in trades:
            if not ((previous is None or trade.day > previous) and trade.day <= day):
                continue
            key = trade.ticker
            symbol = symbol_of(key)
            price = view.price(symbol, trade.day)
            flow += trade.amount
            if trade.quantity > 0 and price:
                book.units[key] = book.units.get(key, 0.0) + trade.amount / price
                book.cost[key] = book.cost.get(key, 0.0) + trade.amount
                shares[key] = shares.get(key, 0.0) + trade.quantity
            elif trade.quantity < 0 and shares.get(key, 0.0) > 0:
                fraction = min(1.0, -trade.quantity / shares[key])
                book.units[key] = book.units.get(key, 0.0) * (1.0 - fraction)
                book.cost[key] = book.cost.get(key, 0.0) * (1.0 - fraction)
                shares[key] -= -trade.quantity
        book.contributed += flow
        book.day = previous = day
        value = sum(u * (view.price(symbol_of(k)) or 0.0) for k, u in book.units.items())
        points.append(
            Point(
                day=day,
                flow=round(flow, 2),
                contributed=round(book.contributed, 2),
                value=round(value, 2),
                cash=0.0,
                fees=0.0,
                taxes=0.0,
            )
        )
    return points, book, shares
