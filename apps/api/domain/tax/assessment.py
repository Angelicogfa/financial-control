"""Monthly income tax on stock exchange gains of an individual (Phase 48.R7, closes TD-04).

Pure: it reads the ledger (trades and corporate events) and returns what the investor owes.

- Sales use the weighted average cost in BRL (each trade converted at its own FX rate), with
  corporate events applied at the start of their ex-date, like `build_position`.
- A buy and a sell of the same asset on the same day are a **day trade** for the matched
  quantity (bought at that day's average, sold at that day's average); the rest of the sale is
  **swing trade** against the average cost of the position held before the day.
- Categories and their own loss carryforward (IN RFB 1.585/2015, arts. 54-58 and 65):
  `COMMON` (ações, ETF, BDR swing trade, 15%; ações exempt when the month's ações sales are
  at most R$ 20 thousand — Lei 11.033/2004, art. 3º I — while ETF and BDR are never exempt),
  `DAY_TRADE` (ações, ETF, BDR, 20%), `FII` (swing and day trade of FII, 20%, no exemption).
  Losses of exempt months still carry forward; exempt gains never absorb losses.
- The withholding (IRRF "dedo-duro") is estimated at 0.005% of the swing sales and 1% of the
  positive day-trade result, and deducted; an excess carries to the next months.
- A DARF (code 6015) below R$ 10 is not paid: it accumulates into the next month. It is due on
  the last business day of the following month (national holidays not considered).
- Applications abroad (ações, ETF and REIT abroad, Lei 14.754/2023, from 2024) are assessed
  per **year** at 15% on the net gain, with the loss carried to the next years; they are paid
  with the annual adjustment (DAA), not by monthly DARF.

Crypto, fixed income (withheld at source) and options are out of this assessment.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from domain.shared.entities import AssetEntity
from domain.shared.enums import AssetType, CorporateEventKind, TransactionKind
from domain.tax.entities import TaxRegime, TaxRuleBook

ZERO = Decimal("0")
CENT = Decimal("0.01")
STOCK_EXEMPTION_BRL = Decimal("20000")  # Lei 11.033/2004, art. 3º, I
DAY_TRADE_RATE = Decimal("0.20")  # Lei 8.981/1995, art. 72; IN RFB 1.585/2015, art. 54
SWING_WITHHOLDING = Decimal("0.00005")  # 0.005% of the sale (IN RFB 1.585/2015, art. 61)
DAY_TRADE_WITHHOLDING = Decimal("0.01")  # 1% of the day-trade result (art. 61, §1º)
MIN_DARF_BRL = Decimal("10")  # Lei 9.430/1996, art. 68
DARF_CODE = "6015"

COMMON_TYPES = frozenset({AssetType.STOCK_BR, AssetType.ETF_BR, AssetType.BDR})
FOREIGN_TYPES = frozenset({AssetType.STOCK_INTL, AssetType.ETF_INTL, AssetType.REIT})


class TaxCategory(StrEnum):
    COMMON = "COMMON"
    DAY_TRADE = "DAY_TRADE"
    FII = "FII"
    FOREIGN_ANNUAL = "FOREIGN_ANNUAL"


MONTHLY_CATEGORIES = (TaxCategory.COMMON, TaxCategory.DAY_TRADE, TaxCategory.FII)


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Sale:
    asset_id: int
    ticker: str
    asset_type: AssetType
    on: date
    quantity: Decimal
    sale_value_brl: Decimal  # gross: quantity x price x FX
    cost_brl: Decimal  # average cost of the quantity sold, fees of the buys included
    fees_brl: Decimal  # fees of the sale
    day_trade: bool

    @property
    def gain_brl(self) -> Decimal:
        return self.sale_value_brl - self.fees_brl - self.cost_brl

    @property
    def category(self) -> TaxCategory:
        if self.asset_type in FOREIGN_TYPES:
            return TaxCategory.FOREIGN_ANNUAL
        if self.asset_type == AssetType.FII:
            return TaxCategory.FII
        return TaxCategory.DAY_TRADE if self.day_trade else TaxCategory.COMMON


@dataclass(frozen=True)
class LedgerIssue:
    ticker: str
    on: date
    message: str


def realized_sales(asset: AssetEntity) -> tuple[list[Sale], list[LedgerIssue]]:
    """Every sale of the asset with its cost, split into day trade and swing trade."""
    if asset.asset_type not in COMMON_TYPES | FOREIGN_TYPES | {AssetType.FII}:
        return [], []
    by_day: dict[date, list] = defaultdict(list)
    for tx in asset.transactions:
        by_day[tx.trade_date].append(tx)
    events = sorted(asset.corporate_events, key=lambda e: (e.ex_date, e.id or 0))
    quantity, cost = ZERO, ZERO  # position before the day, cost in BRL
    sales: list[Sale] = []
    issues: list[LedgerIssue] = []
    for day in sorted(by_day):
        while events and events[0].ex_date <= day:
            event = events.pop(0)
            if quantity > ZERO:
                if event.kind == CorporateEventKind.BONUS:
                    cost += quantity * (event.factor - 1) * event.unit_cost
                quantity = quantity * event.factor
        buys = [t for t in by_day[day] if t.kind == TransactionKind.BUY]
        sells = [t for t in by_day[day] if t.kind == TransactionKind.SELL]

        def fx(t) -> Decimal:
            return t.fx_rate if t.fx_rate > ZERO else Decimal("1")

        bought = sum((t.quantity for t in buys), ZERO)
        buy_cost = sum(((t.quantity * t.unit_price + t.fees) * fx(t) for t in buys), ZERO)
        sold = sum((t.quantity for t in sells), ZERO)
        sale_value = sum((t.quantity * t.unit_price * fx(t) for t in sells), ZERO)
        sale_fees = sum((t.fees * fx(t) for t in sells), ZERO)
        matched = min(bought, sold) if asset.asset_type not in FOREIGN_TYPES else ZERO
        if matched > ZERO:
            share = matched / sold
            sales.append(
                Sale(
                    asset.id or 0,
                    asset.ticker,
                    asset.asset_type,
                    day,
                    matched,
                    sale_value * share,
                    buy_cost * matched / bought,
                    sale_fees * share,
                    day_trade=True,
                )
            )
        swing = sold - matched
        if swing > ZERO:
            if swing > quantity:
                issues.append(
                    LedgerIssue(
                        asset.ticker, day, f"Venda de {swing} sem posição suficiente ({quantity})."
                    )
                )
                swing_cost = cost
            else:
                swing_cost = cost * swing / quantity if quantity > ZERO else ZERO
            share = swing / sold
            sales.append(
                Sale(
                    asset.id or 0,
                    asset.ticker,
                    asset.asset_type,
                    day,
                    swing,
                    sale_value * share,
                    swing_cost,
                    sale_fees * share,
                    day_trade=False,
                )
            )
            quantity = max(quantity - swing, ZERO)
            cost = max(cost - swing_cost, ZERO)
            if quantity == ZERO:
                cost = ZERO
        if bought > matched:
            quantity += bought - matched
            cost += buy_cost * (bought - matched) / bought
    return sales, issues


@dataclass(frozen=True)
class CategoryMonth:
    category: TaxCategory
    sales_brl: Decimal  # gross value sold in the category
    result_brl: Decimal  # gains minus losses of the month
    exempt_gain_brl: Decimal  # ações gains under the R$ 20 thousand exemption
    loss_in_brl: Decimal  # carried loss before the month
    loss_used_brl: Decimal
    loss_out_brl: Decimal  # carried loss after the month
    taxable_brl: Decimal
    rate: Decimal
    tax_brl: Decimal


@dataclass(frozen=True)
class MonthAssessment:
    month: date  # first day
    categories: list[CategoryMonth]
    stock_sales_brl: Decimal  # ações swing sales of the month (the exemption threshold)
    exempt: bool  # ações swing gains exempt this month
    tax_brl: Decimal  # sum of the categories
    withheld_brl: Decimal  # estimated IRRF of the month
    withheld_credit_in_brl: Decimal
    withheld_credit_out_brl: Decimal
    carried_darf_in_brl: Decimal  # DARF below R$ 10 from earlier months
    darf_brl: Decimal  # to pay this month (0 below R$ 10)
    carried_darf_out_brl: Decimal
    due_date: date
    sales: list[Sale] = field(default_factory=list)


@dataclass(frozen=True)
class ForeignYear:
    year: int
    sales_brl: Decimal
    result_brl: Decimal
    loss_in_brl: Decimal
    loss_out_brl: Decimal
    taxable_brl: Decimal
    rate: Decimal
    tax_brl: Decimal


def last_business_day(year: int, month: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    day = nxt - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def darf_due_date(month: date) -> date:
    """Last business day of the month after the sales."""
    following = _next_month(month)
    return last_business_day(following.year, following.month)


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _next_month(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def _rate(book: TaxRuleBook, regime: TaxRegime, on: date) -> Decimal:
    return Decimal(str(book.rate(regime, 0, on)))


def assess_months(
    sales: Iterable[Sale], book: TaxRuleBook, *, through: date
) -> list[MonthAssessment]:
    """Every month from the first sale through `through`, carrying losses, IRRF and DARF."""
    monthly = [s for s in sales if s.category != TaxCategory.FOREIGN_ANNUAL]
    if not monthly:
        return []
    by_month: dict[date, list[Sale]] = defaultdict(list)
    for s in monthly:
        by_month[_month_start(s.on)].append(s)
    losses = {c: ZERO for c in MONTHLY_CATEGORIES}
    credit = ZERO
    carried_darf = ZERO
    out: list[MonthAssessment] = []
    month = min(by_month)
    end = _month_start(through)
    while month <= end:
        items = by_month.get(month, [])
        stock_sales = sum(
            (
                s.sale_value_brl
                for s in items
                if s.category == TaxCategory.COMMON and s.asset_type == AssetType.STOCK_BR
            ),
            ZERO,
        )
        exempt = stock_sales <= STOCK_EXEMPTION_BRL
        categories: list[CategoryMonth] = []
        tax_total = ZERO
        for category in MONTHLY_CATEGORIES:
            rows = [s for s in items if s.category == category]
            sales_value = sum((s.sale_value_brl for s in rows), ZERO)
            exempt_gain = ZERO
            result = ZERO
            for s in rows:
                gain = s.gain_brl
                if (
                    category == TaxCategory.COMMON
                    and exempt
                    and s.asset_type == AssetType.STOCK_BR
                    and gain > ZERO
                ):
                    exempt_gain += gain
                else:
                    result += gain
            loss_in = losses[category]
            if result > ZERO:
                used = min(loss_in, result)
                taxable = result - used
                loss_out = loss_in - used
            else:
                used = ZERO
                taxable = ZERO
                loss_out = loss_in - result
            if category == TaxCategory.COMMON:
                rate = _rate(book, TaxRegime.STOCK_SWING_TRADE, month)
            elif category == TaxCategory.FII:
                rate = _rate(book, TaxRegime.FII_CAPITAL_GAIN, month)
            else:
                rate = DAY_TRADE_RATE
            tax = _money(taxable * rate)
            losses[category] = loss_out
            tax_total += tax
            if rows or loss_in > ZERO:
                categories.append(
                    CategoryMonth(
                        category,
                        _money(sales_value),
                        _money(result),
                        _money(exempt_gain),
                        _money(loss_in),
                        _money(used),
                        _money(loss_out),
                        _money(taxable),
                        rate,
                        tax,
                    )
                )
        day_results: dict[date, Decimal] = defaultdict(lambda: ZERO)
        for s in items:
            if s.day_trade and s.category == TaxCategory.DAY_TRADE:
                day_results[s.on] += s.gain_brl
        withheld = _money(
            sum((s.sale_value_brl for s in items if not s.day_trade), ZERO) * SWING_WITHHOLDING
            + sum((max(v, ZERO) for v in day_results.values()), ZERO) * DAY_TRADE_WITHHOLDING
        )
        available = credit + withheld
        net = tax_total - available
        credit_out = max(-net, ZERO)
        due = max(net, ZERO) + carried_darf
        darf = due if due >= MIN_DARF_BRL else ZERO
        carried_out = due - darf
        out.append(
            MonthAssessment(
                month=month,
                categories=categories,
                stock_sales_brl=_money(stock_sales),
                exempt=exempt,
                tax_brl=_money(tax_total),
                withheld_brl=withheld,
                withheld_credit_in_brl=_money(credit),
                withheld_credit_out_brl=_money(credit_out),
                carried_darf_in_brl=_money(carried_darf),
                darf_brl=_money(darf),
                carried_darf_out_brl=_money(carried_out),
                due_date=darf_due_date(month),
                sales=sorted(items, key=lambda s: (s.on, s.ticker)),
            )
        )
        credit = credit_out
        carried_darf = carried_out
        month = _next_month(month)
    return out


def assess_foreign(sales: Iterable[Sale], book: TaxRuleBook, *, through: date) -> list[ForeignYear]:
    """Applications abroad: one assessment per year from 2024 (Lei 14.754/2023)."""
    abroad = [s for s in sales if s.category == TaxCategory.FOREIGN_ANNUAL and s.on.year >= 2024]
    if not abroad:
        return []
    by_year: dict[int, list[Sale]] = defaultdict(list)
    for s in abroad:
        by_year[s.on.year].append(s)
    loss = ZERO
    years: list[ForeignYear] = []
    for year in range(min(by_year), through.year + 1):
        rows = by_year.get(year, [])
        result = sum((s.gain_brl for s in rows), ZERO)
        loss_in = loss
        if result > ZERO:
            used = min(loss, result)
            taxable = result - used
            loss = loss - used
        else:
            taxable = ZERO
            loss = loss - result
        rate = _rate(book, TaxRegime.FOREIGN_ANNUAL, date(year, 12, 31))
        years.append(
            ForeignYear(
                year,
                _money(sum((s.sale_value_brl for s in rows), ZERO)),
                _money(result),
                _money(loss_in),
                _money(loss),
                _money(taxable),
                rate,
                _money(taxable * rate),
            )
        )
    return years
