"""Strategy backtest (Phase 33.2, design section 3): the real contribution rules replayed.

Every last business day of the month the engine:
1. reads prices through a point-in-time view (never data after that day);
2. grows the uninvested cash by the cash index (CDI) since the previous step;
3. adds the month's contribution (optionally corrected by the previous month's IPCA);
4. consolidates the simulated portfolio and splits the cash with `plan_contribution`, the
   same two-level ARCA rules (targets, bands, intra-class strategy) of the real contribution;
5. books the purchases with fees and records the portfolio value.

Prices are total-return series in BRL, so there is no separate dividend credit (risk R7).
Selling and rebalancing are not simulated yet: the strategy only contributes, like the real
one, so there is no income tax to pay. The checklist is not replayed (no answers existed in
the past); every asset follows the "not evaluated" eligibility rule.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from domain.market.entities import Quote
from domain.policy.services.policy import InvestmentPolicy
from domain.portfolio.services.analytics import (
    annualized_volatility,
    cagr,
    cumulative_return,
    dated_time_weighted_returns,
    max_drawdown,
)
from domain.portfolio.services.consolidation import consolidate_portfolio, plan_contribution
from domain.shared.entities import AssetEntity, PortfolioSnapshotEntity, TransactionEntity
from domain.shared.enums import ArcaClass, AssetType, TransactionKind
from domain.simulation.market import MarketHistory, PointInTimeView, month_ends

MONTHS_PER_YEAR = 12.0
QUANTITY_DECIMALS = Decimal("0.00000001")
PRICE_DECIMALS = Decimal("0.00000001")


@dataclass(frozen=True)
class SimulatedAsset:
    """An asset the strategy may buy; `price_symbol` names its series in the history."""

    ticker: str
    name: str
    asset_type: AssetType
    arca_class: ArcaClass
    price_symbol: str | None = None

    @property
    def symbol(self) -> str:
        return self.price_symbol or self.ticker


@dataclass(frozen=True)
class BacktestConfig:
    start: date
    end: date
    monthly_contribution: float
    initial_contribution: float = 0.0
    correct_by_ipca: bool = False
    fee_rate: float = 0.0003  # B3 trading fees (emolumentos) on each purchase
    cash_symbol: str | None = "CDI"  # uninvested cash follows this index (None = 0%)


@dataclass(frozen=True)
class BacktestPoint:
    day: date
    contribution: float
    contributed: float
    market_value: float
    cash: float
    fees: float
    by_class: dict[ArcaClass, float] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestSummary:
    final_value: float
    contributed: float
    gain: float
    money_weighted_return: float | None  # annual IRR of the contributions
    time_weighted_return: float  # cumulative TWR
    annual_twr: float
    volatility: float
    max_drawdown: float
    trades: int
    fees: float


@dataclass(frozen=True)
class BacktestResult:
    label: str
    points: list[BacktestPoint]
    summary: BacktestSummary
    unavailable: list[str] = field(default_factory=list)


def _contribution_schedule(
    view_for: Callable[[date], PointInTimeView], config: BacktestConfig, days: Sequence[date]
) -> list[float]:
    """Monthly amounts; with IPCA correction each month grows by the previous month's IPCA."""
    amounts: list[float] = []
    base = config.monthly_contribution
    for index, day in enumerate(days):
        if index > 0 and config.correct_by_ipca:
            prev = days[index - 1]
            ipca = view_for(day).ipca(prev.year, prev.month)
            base *= 1.0 + (ipca or 0.0)
        amounts.append(base + (config.initial_contribution if index == 0 else 0.0))
    return amounts


def _cash_growth(view: PointInTimeView, symbol: str | None, previous: date | None) -> float:
    if symbol is None or previous is None:
        return 1.0
    now, before = view.price(symbol), view.price(symbol, previous)
    if not now or not before:
        return 1.0
    return now / before


def money_weighted_return(
    flows: Sequence[tuple[date, float]], final: tuple[date, float]
) -> float | None:
    """Annual IRR of contributions (negative flows) and the final value, by bisection."""
    cash = [*((d, -v) for d, v in flows if v), final]
    if len(cash) < 2 or not any(v < 0 for _, v in cash) or final[1] <= 0:
        return None
    origin = cash[0][0]

    def npv(rate: float) -> float:
        return sum(v / (1.0 + rate) ** ((d - origin).days / 365.0) for d, v in cash)

    low, high = -0.99, 10.0
    if npv(low) * npv(high) > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2.0
        if npv(low) * npv(mid) <= 0:
            high = mid
        else:
            low = mid
    return round((low + high) / 2.0, 6)


def _summary(points: Sequence[BacktestPoint], trades: int) -> BacktestSummary:
    snapshots = [
        PortfolioSnapshotEntity(
            snapshot_date=p.day,
            invested_value=p.contributed,
            market_value=p.market_value,
            unrealized_pnl=p.market_value - p.contributed,
            net_flow=p.contribution,
        )
        for p in points
    ]
    _dates, returns = dated_time_weighted_returns(snapshots)
    last = points[-1] if points else None
    twr = cumulative_return(returns)
    return BacktestSummary(
        final_value=round(last.market_value, 2) if last else 0.0,
        contributed=round(last.contributed, 2) if last else 0.0,
        gain=round(last.market_value - last.contributed, 2) if last else 0.0,
        money_weighted_return=(
            money_weighted_return(
                [(p.day, p.contribution) for p in points], (last.day, last.market_value)
            )
            if last
            else None
        ),
        time_weighted_return=round(twr, 6),
        annual_twr=round(cagr(twr, len(returns), MONTHS_PER_YEAR), 6),
        volatility=round(annualized_volatility(returns, MONTHS_PER_YEAR), 6),
        max_drawdown=round(max_drawdown(returns), 6),
        trades=trades,
        fees=round(last.fees, 2) if last else 0.0,
    )


def run_backtest(
    assets: Sequence[SimulatedAsset],
    history: MarketHistory,
    policy: InvestmentPolicy,
    config: BacktestConfig,
    *,
    label: str = "Estratégia",
) -> BacktestResult:
    """Replay the policy's monthly contributions over the history (see module docstring)."""
    days = month_ends(config.start, config.end)
    amounts = _contribution_schedule(history.view, config, days)
    targets = policy.arca.targets
    transactions: dict[str, list[TransactionEntity]] = {a.ticker: [] for a in assets}
    quantities: dict[str, float] = {a.ticker: 0.0 for a in assets}
    ids = {a.ticker: index + 1 for index, a in enumerate(assets)}
    cash = contributed = fees = 0.0
    trades = 0
    points: list[BacktestPoint] = []
    seen: set[str] = set()
    previous: date | None = None

    for day, amount in zip(days, amounts, strict=True):
        view = history.view(day)
        cash = cash * _cash_growth(view, config.cash_symbol, previous) + amount
        contributed += amount
        live = [a for a in assets if view.available(a.symbol)]
        seen.update(a.ticker for a in live)
        prices = {a.ticker: view.price(a.symbol) or 0.0 for a in live}
        entities = [
            AssetEntity(
                id=ids[a.ticker],
                ticker=a.ticker,
                name=a.name,
                asset_type=a.asset_type,
                arca_class=a.arca_class,
                currency="BRL",
                use_cerrado=False,
                transactions=tuple(transactions[a.ticker]),
            )
            for a in live
        ]
        if entities and cash > 0:
            report = consolidate_portfolio(
                entities,
                targets,
                quotes={t: Quote(symbol=t, price=p) for t, p in prices.items() if p > 0},
                intra_strategies=policy.arca.strategies,
                bands=policy.arca.bands,
                eligibility=policy.eligibility,
                usd_brl_rate=1.0,
                as_of_date=day,
            )
            plan = plan_contribution(report, targets, cash)
            for order in plan.orders:
                price = prices.get(order.ticker, 0.0)
                qty = Decimal(str(order.recommended_quantity)).quantize(QUANTITY_DECIMALS)
                if price <= 0 or qty <= 0:
                    continue
                spent = float(qty) * price
                fee = spent * config.fee_rate
                transactions[order.ticker].append(
                    TransactionEntity(
                        asset_id=ids[order.ticker],
                        kind=TransactionKind.BUY,
                        trade_date=day,
                        quantity=qty,
                        unit_price=Decimal(str(price)).quantize(PRICE_DECIMALS),
                        fees=Decimal(str(round(fee, 8))),
                    )
                )
                quantities[order.ticker] += float(qty)
                cash -= spent + fee
                fees += fee
                trades += 1

        by_class: dict[ArcaClass, float] = {}
        for a in live:
            value = quantities[a.ticker] * prices[a.ticker]
            by_class[a.arca_class] = by_class.get(a.arca_class, 0.0) + value
        invested = sum(by_class.values())
        points.append(
            BacktestPoint(
                day=day,
                contribution=round(amount, 2),
                contributed=round(contributed, 2),
                market_value=round(invested + cash, 2),
                cash=round(cash, 2),
                fees=round(fees, 2),
                by_class={c: round(v, 2) for c, v in by_class.items()},
            )
        )
        previous = day

    return BacktestResult(
        label=label,
        points=points,
        summary=_summary(points, trades),
        unavailable=sorted(a.ticker for a in assets if a.ticker not in seen),
    )


def run_benchmark(
    symbol: str,
    history: MarketHistory,
    config: BacktestConfig,
    *,
    label: str | None = None,
) -> BacktestResult:
    """The same contribution flow invested entirely in one series (fractional, with fees)."""
    days = month_ends(config.start, config.end)
    amounts = _contribution_schedule(history.view, config, days)
    units = contributed = fees = cash = 0.0
    points: list[BacktestPoint] = []
    previous: date | None = None
    trades = 0
    for day, amount in zip(days, amounts, strict=True):
        view = history.view(day)
        cash = cash * _cash_growth(view, config.cash_symbol, previous) + amount
        contributed += amount
        price = view.price(symbol)
        if price and cash > 0:
            fee = cash * config.fee_rate / (1.0 + config.fee_rate)
            units += (cash - fee) / price
            fees += fee
            cash = 0.0
            trades += 1
        value = units * (price or 0.0) + cash
        points.append(
            BacktestPoint(
                day=day,
                contribution=round(amount, 2),
                contributed=round(contributed, 2),
                market_value=round(value, 2),
                cash=round(cash, 2),
                fees=round(fees, 2),
            )
        )
        previous = day
    return BacktestResult(label=label or symbol, points=points, summary=_summary(points, trades))
