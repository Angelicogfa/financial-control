"""Strategy backtest (Phase 33.2, design section 3): the real contribution rules replayed.

Every last business day of the month the engine:
1. reads prices through a point-in-time view (never data after that day);
2. grows the uninvested cash by the cash index (CDI) since the previous step;
3. adds the month's contribution (optionally corrected by the previous month's IPCA);
4. with `rebalance`, sells what exceeds the band in each ARCA class back to its target, at the
   average cost, paying the income tax of the asset type (stocks exempt up to R$ 20 mil of
   sales in the month; losses are not carried forward, which is conservative);
5. consolidates the simulated portfolio and splits the cash with `plan_contribution`, the
   same two-level ARCA rules (targets, bands, intra-class strategy) of the real contribution;
6. books the purchases with fees and records the portfolio value.

The policy is fixed (the current rules over the whole history, decision 5) or, with
`policy_versions`, the version in force on each date. Manual checklist answers apply from
their `answered_at` on; before an asset has answers it follows the "not evaluated" rule.
Prices are total-return series in BRL, so there is no separate dividend credit (risk R7).
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
from domain.shared.entities import (
    AssetEntity,
    ChecklistAnswer,
    PortfolioSnapshotEntity,
    TransactionEntity,
)
from domain.shared.enums import (
    INTEGER_QUANTITY_TYPES,
    ArcaClass,
    AssetType,
    ChecklistProfile,
    TransactionKind,
)
from domain.simulation.market import MarketHistory, PointInTimeView, month_ends
from domain.tax.entities import TaxRuleBook
from domain.tax.services.rules import DEFAULT_RULE_BOOK, REGIMES_BY_ASSET_TYPE

MONTHS_PER_YEAR = 12.0
QUANTITY_DECIMALS = Decimal("0.00000001")
PRICE_DECIMALS = Decimal("0.00000001")
# Sales of Brazilian stocks up to this amount in a month are exempt (Lei 11.033/2004).
STOCK_MONTHLY_EXEMPTION_BRL = 20_000.0
# Stored with every run: results are reused only for the same engine version (Phase 33.3).
ENGINE_VERSION = "33.6.0"


class SimulationTimeout(Exception):
    """The run went past its time limit."""


def _check(deadline: Callable[[], bool] | None) -> None:
    if deadline is not None and deadline():
        raise SimulationTimeout("simulation time limit reached")


@dataclass(frozen=True)
class SimulatedAsset:
    """An asset the strategy may buy; `price_symbol` names its series in the history."""

    ticker: str
    name: str
    asset_type: AssetType
    arca_class: ArcaClass
    price_symbol: str | None = None
    # Full manual answer history (append-only); each answer counts from `answered_at`.
    answers: tuple[ChecklistAnswer, ...] = ()
    use_cerrado: bool = True
    checklist_profile: ChecklistProfile | None = None
    # Picked from the B3 catalog of today: only survivors are listed (risk R2).
    from_catalog: bool = False

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
    rebalance: bool = False  # sell above-band classes back to target every month


@dataclass(frozen=True)
class BacktestPoint:
    day: date
    contribution: float
    contributed: float
    market_value: float
    cash: float
    fees: float
    taxes: float = 0.0
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
    taxes: float = 0.0
    sales: int = 0


@dataclass(frozen=True)
class BacktestResult:
    label: str
    points: list[BacktestPoint]
    summary: BacktestSummary
    unavailable: list[str] = field(default_factory=list)
    # True when catalog assets took part: the universe only has today's survivors.
    survivorship_bias: bool = False


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


def _summary(points: Sequence[BacktestPoint], trades: int, sales: int = 0) -> BacktestSummary:
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
        taxes=round(last.taxes, 2) if last else 0.0,
        sales=sales,
    )


def answers_on(asset: SimulatedAsset, day: date) -> dict[str, ChecklistAnswer]:
    """The manual answer in force for each question at the close of `day`."""
    current: dict[str, ChecklistAnswer] = {}
    for answer in sorted(
        (a for a in asset.answers if a.answered_at is not None),
        key=lambda a: a.answered_at,  # type: ignore[arg-type,return-value]
    ):
        if answer.answered_at.date() > day:  # type: ignore[union-attr]
            break
        if answer.value is None:
            current.pop(answer.question_id, None)
        else:
            current[answer.question_id] = answer
    return current


def policy_on(
    day: date, policy: InvestmentPolicy, versions: Sequence[InvestmentPolicy]
) -> InvestmentPolicy:
    """The version in force on `day` (the first one before it existed).

    Without versions, the fixed `policy` applies on every date.
    """
    dated = sorted((v for v in versions if v.created_at is not None), key=lambda v: v.created_at)  # type: ignore[arg-type,return-value]
    if not dated:
        return policy
    chosen = dated[0]
    for version in dated:
        if version.created_at.date() <= day:  # type: ignore[union-attr]
            chosen = version
    return chosen


def sale_tax_rate(asset_type: AssetType, day: date, holding_days: int, rules: TaxRuleBook) -> float:
    """Income tax on the gain of a sale for the asset type (first regime of the type)."""
    regime = REGIMES_BY_ASSET_TYPE[asset_type][0]
    return rules.rule(regime, day).rate_for(holding_days)


@dataclass
class _Holding:
    asset: SimulatedAsset
    asset_id: int
    quantity: float = 0.0
    cost: float = 0.0
    first_buy: date | None = None
    transactions: list[TransactionEntity] = field(default_factory=list)

    @property
    def average(self) -> float:
        return self.cost / self.quantity if self.quantity > 0 else 0.0


def _rebalance_sales(
    holdings: dict[str, _Holding],
    live: Sequence[SimulatedAsset],
    prices: dict[str, float],
    cash: float,
    policy: InvestmentPolicy,
) -> dict[str, float]:
    """Quantity to sell per ticker so that every class above its band returns to target."""
    by_class: dict[ArcaClass, list[SimulatedAsset]] = {}
    for a in live:
        by_class.setdefault(a.arca_class, []).append(a)
    values = {
        c: sum(holdings[a.ticker].quantity * prices[a.ticker] for a in members)
        for c, members in by_class.items()
    }
    total = sum(values.values()) + cash
    if total <= 0:
        return {}
    sales: dict[str, float] = {}
    for arca_class, members in by_class.items():
        target = policy.arca.classes[arca_class].target_pct
        band = policy.arca.classes[arca_class].band_pct
        value = values[arca_class]
        if value <= 0 or value / total * 100.0 <= target + band:
            continue
        excess = value - target / 100.0 * total
        for a in members:
            held = holdings[a.ticker].quantity * prices[a.ticker]
            if held <= 0:
                continue
            qty = min(holdings[a.ticker].quantity, excess * held / value / prices[a.ticker])
            if a.asset_type in INTEGER_QUANTITY_TYPES:
                qty = float(int(qty))
            if qty > 0:
                sales[a.ticker] = qty
    return sales


def run_backtest(
    assets: Sequence[SimulatedAsset],
    history: MarketHistory,
    policy: InvestmentPolicy,
    config: BacktestConfig,
    *,
    label: str = "Estratégia",
    policy_versions: Sequence[InvestmentPolicy] = (),
    tax_rules: TaxRuleBook | None = None,
    deadline: Callable[[], bool] | None = None,
) -> BacktestResult:
    """Replay the policy's monthly contributions over the history (see module docstring).

    `deadline` is polled every month; when it returns True the run stops with
    `SimulationTimeout`.
    """
    days = month_ends(config.start, config.end)
    amounts = _contribution_schedule(history.view, config, days)
    rules = tax_rules or DEFAULT_RULE_BOOK
    holdings = {a.ticker: _Holding(a, index + 1) for index, a in enumerate(assets)}
    cash = contributed = fees = taxes = 0.0
    trades = sales_count = 0
    points: list[BacktestPoint] = []
    seen: set[str] = set()
    previous: date | None = None

    def book(
        holding: _Holding, kind: TransactionKind, qty: float, price: float, fee: float, day: date
    ) -> None:
        holding.transactions.append(
            TransactionEntity(
                asset_id=holding.asset_id,
                kind=kind,
                trade_date=day,
                quantity=Decimal(str(qty)).quantize(QUANTITY_DECIMALS),
                unit_price=Decimal(str(price)).quantize(PRICE_DECIMALS),
                fees=Decimal(str(round(fee, 8))),
            )
        )

    for day, amount in zip(days, amounts, strict=True):
        _check(deadline)
        view = history.view(day)
        rules_today = policy_on(day, policy, policy_versions)
        targets = rules_today.arca.targets
        cash = cash * _cash_growth(view, config.cash_symbol, previous) + amount
        contributed += amount
        live = [a for a in assets if view.available(a.symbol)]
        seen.update(a.ticker for a in live)
        prices = {a.ticker: view.price(a.symbol) or 0.0 for a in live}

        if config.rebalance:
            planned = _rebalance_sales(holdings, live, prices, cash, rules_today)
            # The R$ 20 mil exemption looks at all stock sales of the month together.
            stock_sales = sum(
                qty * prices[t]
                for t, qty in planned.items()
                if holdings[t].asset.asset_type == AssetType.STOCK_BR
            )
            stocks_exempt = stock_sales <= STOCK_MONTHLY_EXEMPTION_BRL
            for ticker, qty in planned.items():
                holding = holdings[ticker]
                price = prices[ticker]
                gross = qty * price
                fee = gross * config.fee_rate
                gain = qty * (price - holding.average)
                holding_days = (day - holding.first_buy).days if holding.first_buy else 0
                book(holding, TransactionKind.SELL, qty, price, fee, day)
                holding.cost -= qty * holding.average
                holding.quantity -= qty
                cash += gross - fee
                fees += fee
                trades += 1
                sales_count += 1
                if holding.asset.asset_type == AssetType.STOCK_BR and stocks_exempt:
                    continue
                rate = sale_tax_rate(holding.asset.asset_type, day, holding_days, rules)
                tax = max(0.0, gain) * rate
                cash -= tax
                taxes += tax

        entities = [
            AssetEntity(
                id=holdings[a.ticker].asset_id,
                ticker=a.ticker,
                name=a.name,
                asset_type=a.asset_type,
                arca_class=a.arca_class,
                currency="BRL",
                use_cerrado=a.use_cerrado,
                checklist_profile=a.checklist_profile,
                cerrado_answers=answers_on(a, day),
                transactions=tuple(holdings[a.ticker].transactions),
            )
            for a in live
        ]
        if entities and cash > 0:
            report = consolidate_portfolio(
                entities,
                targets,
                quotes={t: Quote(symbol=t, price=p) for t, p in prices.items() if p > 0},
                intra_strategies=rules_today.arca.strategies,
                bands=rules_today.arca.bands,
                eligibility=rules_today.eligibility,
                usd_brl_rate=1.0,
                as_of_date=day,
            )
            plan = plan_contribution(report, targets, cash)
            for order in plan.orders:
                price = prices.get(order.ticker, 0.0)
                qty = float(Decimal(str(order.recommended_quantity)).quantize(QUANTITY_DECIMALS))
                if price <= 0 or qty <= 0:
                    continue
                holding = holdings[order.ticker]
                spent = qty * price
                fee = spent * config.fee_rate
                book(holding, TransactionKind.BUY, qty, price, fee, day)
                holding.quantity += qty
                holding.cost += spent + fee
                holding.first_buy = holding.first_buy or day
                cash -= spent + fee
                fees += fee
                trades += 1

        by_class: dict[ArcaClass, float] = {}
        for a in live:
            value = holdings[a.ticker].quantity * prices[a.ticker]
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
                taxes=round(taxes, 2),
                by_class={c: round(v, 2) for c, v in by_class.items()},
            )
        )
        previous = day

    return BacktestResult(
        label=label,
        points=points,
        summary=_summary(points, trades, sales_count),
        unavailable=sorted(a.ticker for a in assets if a.ticker not in seen),
        survivorship_bias=any(a.from_catalog and a.ticker in seen for a in assets),
    )


def run_benchmark(
    symbol: str,
    history: MarketHistory,
    config: BacktestConfig,
    *,
    label: str | None = None,
    deadline: Callable[[], bool] | None = None,
) -> BacktestResult:
    """The same contribution flow invested entirely in one series (fractional, with fees)."""
    days = month_ends(config.start, config.end)
    amounts = _contribution_schedule(history.view, config, days)
    units = contributed = fees = cash = 0.0
    points: list[BacktestPoint] = []
    previous: date | None = None
    trades = 0
    for day, amount in zip(days, amounts, strict=True):
        _check(deadline)
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
