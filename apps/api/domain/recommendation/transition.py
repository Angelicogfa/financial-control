"""How to reach a class's targets (Phase 34.7), the same targets the contribution follows.

A study, never an order. Two paths, side by side:

- contributions only: the monthly amount goes to the assets below target, with no sale and no
  tax; the path counts the months until the class is close to the target, without any return.
- with sales: the excess of what sits above target is sold in whole units and the proceeds buy
  what sits below. The income tax is the difference the sales make in the real assessment
  (`domain/tax/assessment.py`): the R$ 20 thousand exemption, the losses carried and the sales
  already made in the month all count. When the stock sales pass the exemption, the same sales
  are also assessed split over the months that keep them within it.

The sales are worth it only if the expected gain pays for them: the expected return of each
asset over the class is the declared premise of the matrix, not a tested one.
"""

from __future__ import annotations

import calendar
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from domain.comparison.engine import FEE_RATE
from domain.shared.enums import INTEGER_QUANTITY_TYPES, AssetType
from domain.tax.assessment import (
    STOCK_EXEMPTION_BRL,
    Sale,
    assess_foreign,
    assess_months,
)
from domain.tax.entities import TaxRuleBook

TOLERANCE = 0.05  # close enough: 5% of the class out of place
MAX_MONTHS = 240
MAX_SPLIT_MONTHS = 24
PAYBACK_HORIZON_MONTHS = 36  # the sales pay off if the expected gain covers them by then
MIN_SALE_BRL = 1.0  # below this, rounding, not a sale
ZERO = Decimal("0")


@dataclass(frozen=True)
class TransitionHolding:
    asset_id: int
    ticker: str
    asset_type: AssetType
    quantity: float
    value_brl: float
    invested_brl: float


@dataclass(frozen=True)
class TransitionLine:
    ticker: str
    current_weight: float
    target_weight: float
    current_brl: float
    target_brl: float
    next_contribution_brl: float
    buy_brl: float


@dataclass(frozen=True)
class TransitionSale:
    ticker: str
    asset_type: str
    quantity: float
    value_brl: float
    cost_brl: float
    gain_brl: float


@dataclass(frozen=True)
class Transition:
    total_brl: float
    distance: float
    monthly_brl: float
    months: int | None
    tolerance: float
    lines: list[TransitionLine] = field(default_factory=list)
    sales: list[TransitionSale] = field(default_factory=list)
    sold_brl: float = 0.0
    tax_brl: float = 0.0
    fees_brl: float = 0.0
    cost_brl: float = 0.0
    split_months: int | None = None
    split_tax_brl: float | None = None
    expected_gain_year_brl: float = 0.0
    payback_months: float | None = None
    pays_off: bool = False
    payback_horizon_months: int = PAYBACK_HORIZON_MONTHS


def distance_to(values: Mapping[str, float], targets: Mapping[str, float]) -> float:
    """The share of the class that would have to change places to match the targets."""
    total = sum(values.values())
    if total <= 0:
        return 1.0 if targets else 0.0
    tickers = set(values) | set(targets)
    return 0.5 * sum(abs(values.get(t, 0.0) / total - targets.get(t, 0.0)) for t in tickers)


def _deficits(
    values: Mapping[str, float], targets: Mapping[str, float], total: float
) -> dict[str, float]:
    return {t: max(w * total - values.get(t, 0.0), 0.0) for t, w in targets.items()}


def _shared(amount: float, deficits: Mapping[str, float]) -> dict[str, float]:
    """`amount` over the deficits, proportionally, never more than each one needs."""
    gap = sum(deficits.values())
    if gap <= 0 or amount <= 0:
        return {}
    scale = min(amount / gap, 1.0)
    return {t: d * scale for t, d in deficits.items() if d > 0}


def contribution_path(
    values: Mapping[str, float], targets: Mapping[str, float], monthly_brl: float
) -> tuple[int | None, dict[str, float]]:
    """(months until the class is within the tolerance, the first month's contribution)."""
    current = dict(values)
    first: dict[str, float] = {}
    for month in range(MAX_MONTHS + 1):
        if distance_to(current, targets) <= TOLERANCE:
            return month, first
        if monthly_brl <= 0:
            return None, first
        share = _shared(
            monthly_brl, _deficits(current, targets, sum(current.values()) + monthly_brl)
        )
        if month == 0:
            first = share
        for t, v in share.items():
            current[t] = current.get(t, 0.0) + v
    return None, first


def _money(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))


def _sale(h: TransitionHolding, units: float, on: date) -> Sale:
    unit_value = h.value_brl / h.quantity
    unit_cost = h.invested_brl / h.quantity
    value = units * unit_value
    return Sale(
        asset_id=h.asset_id,
        ticker=h.ticker,
        asset_type=h.asset_type,
        on=on,
        quantity=Decimal(str(units)),
        sale_value_brl=_money(value),
        cost_brl=_money(units * unit_cost),
        fees_brl=_money(value * FEE_RATE),
        day_trade=False,
    )


def _tax_of(sales: Sequence[Sale], book: TaxRuleBook, through: date) -> Decimal:
    monthly = sum((m.tax_brl for m in assess_months(sales, book, through=through)), ZERO)
    foreign = sum((y.tax_brl for y in assess_foreign(sales, book, through=through)), ZERO)
    return monthly + foreign


def added_tax(
    past: Sequence[Sale], new: Sequence[Sale], book: TaxRuleBook, through: date
) -> Decimal:
    """What `new` adds to the assessment of the sales already made (never below zero)."""
    return max(_tax_of([*past, *new], book, through) - _tax_of(past, book, through), ZERO)


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def split_sales(sales: Sequence[Sale], months: int) -> list[Sale]:
    """The stock sales in equal parts over `months`, the others in the first month."""
    out: list[Sale] = []
    for s in sales:
        if s.asset_type != AssetType.STOCK_BR:
            out.append(s)
            continue
        parts = Decimal(months)
        for i in range(months):
            out.append(
                Sale(
                    asset_id=s.asset_id,
                    ticker=s.ticker,
                    asset_type=s.asset_type,
                    on=_add_months(s.on, i),
                    quantity=s.quantity / parts,
                    sale_value_brl=s.sale_value_brl / parts,
                    cost_brl=s.cost_brl / parts,
                    fees_brl=s.fees_brl / parts,
                    day_trade=False,
                )
            )
    return out


def plan_transition(
    *,
    holdings: Sequence[TransitionHolding],
    targets: Mapping[str, float],
    expected: Mapping[str, float],
    monthly_brl: float,
    past_sales: Sequence[Sale],
    book: TaxRuleBook,
    today: date,
) -> Transition:
    values = {h.ticker: h.value_brl for h in holdings if h.value_brl > 0}
    total = sum(values.values())
    months, first = contribution_path(values, targets, monthly_brl)

    # Within the tolerance there is nothing to change: no sale, as in the contributions path.
    sales: list[Sale] = []
    for h in holdings if distance_to(values, targets) > TOLERANCE else ():
        excess = h.value_brl - targets.get(h.ticker, 0.0) * total
        unit_value = h.value_brl / h.quantity if h.quantity > 0 else 0.0
        units = min(excess / unit_value, h.quantity) if unit_value > 0 else 0.0
        if h.asset_type in INTEGER_QUANTITY_TYPES:
            units = float(math.floor(units))
        if units * unit_value >= MIN_SALE_BRL:
            sales.append(_sale(h, units, today))
    sold = float(sum((s.sale_value_brl for s in sales), ZERO))
    tax = added_tax(past_sales, sales, book, today) if sales else ZERO

    split_months = None
    split_tax = None
    stock_sold = sum((s.sale_value_brl for s in sales if s.asset_type == AssetType.STOCK_BR), ZERO)
    if stock_sold > STOCK_EXEMPTION_BRL:
        needed = math.ceil(stock_sold / STOCK_EXEMPTION_BRL)
        if needed <= MAX_SPLIT_MONTHS:
            split_months = needed
            parts = split_sales(sales, needed)
            split_tax = float(added_tax(past_sales, parts, book, _add_months(today, needed - 1)))

    sale_fees = float(sum((s.fees_brl for s in sales), ZERO))
    left = dict(values)
    for s in sales:
        left[s.ticker] = left.get(s.ticker, 0.0) - float(s.sale_value_brl)
    proceeds = max(sold - sale_fees - float(tax), 0.0)
    buys = _shared(proceeds, _deficits(left, targets, total))
    buy_fees = sum(buys.values()) * FEE_RATE
    fees = sale_fees + buy_fees
    cost = float(tax) + fees

    after = dict(left)
    for t, v in buys.items():
        after[t] = after.get(t, 0.0) + v
    gain = 0.0
    if total > 0:
        gain = sum(
            (after.get(t, 0.0) - values.get(t, 0.0)) * expected.get(t, 0.0)
            for t in set(after) | set(values)
        )
    payback = cost / (gain / 12.0) if gain > 0 and cost > 0 else None

    lines = [
        TransitionLine(
            ticker=t,
            current_weight=round(values.get(t, 0.0) / total, 6) if total > 0 else 0.0,
            target_weight=round(targets.get(t, 0.0), 6),
            current_brl=round(values.get(t, 0.0), 2),
            target_brl=round(targets.get(t, 0.0) * total, 2),
            next_contribution_brl=round(first.get(t, 0.0), 2),
            buy_brl=round(buys.get(t, 0.0), 2),
        )
        for t in sorted(set(values) | set(targets), key=lambda k: (-targets.get(k, 0.0), k))
    ]
    return Transition(
        total_brl=round(total, 2),
        distance=round(distance_to(values, targets), 6),
        monthly_brl=monthly_brl,
        months=months,
        tolerance=TOLERANCE,
        lines=lines,
        sales=[
            TransitionSale(
                ticker=s.ticker,
                asset_type=s.asset_type.value,
                quantity=float(s.quantity),
                value_brl=float(s.sale_value_brl),
                cost_brl=float(s.cost_brl),
                gain_brl=float(s.gain_brl),
            )
            for s in sales
        ],
        sold_brl=round(sold, 2),
        tax_brl=float(tax),
        fees_brl=round(fees, 2),
        cost_brl=round(cost, 2),
        split_months=split_months,
        split_tax_brl=split_tax,
        expected_gain_year_brl=round(gain, 2),
        payback_months=round(payback, 1) if payback is not None else None,
        pays_off=payback is not None and payback <= PAYBACK_HORIZON_MONTHS,
    )
