"""Automatic fixed income valuation along contracted indexer curves (CDI, SELIC, IPCA+, Pre).

Conventions (ADR 0006):
- Curves are canonical fractions: daily CDI/SELIC rates per business day and monthly IPCA
  rates keyed by (year, month). Missing points fall back to the annual rate of `RateCurves`
  and are reported through `curve_coverage`.
- `contracted_rate` is a multiplier for CDI/SELIC (1.10 = 110% of the index) and an annual
  fraction for PRE/IPCA (0.065 = 6.5% a.a.).
- IPCA+ accrues each month's IPCA pro-rata by business days inside the month, compounded
  with the real rate over 252 business days per year.
- Business days follow the national holiday calendar (`fincontrol_core.calendar`).
- Every lot accrues from its own purchase (trade) date; the issue date of the terms is
  informational only and never changes the valuation.
- Zero-coupon Tesouro Prefixado (LTN) lots accrue at the rate implied by the unit price paid
  (PU = 1000 / (1 + r) ^ (business days to maturity / 252)), so each purchase keeps the rate
  it was actually bought at; `contracted_rate` is only the fallback when it cannot be implied.
- Redemptions (SELL) are gross amounts taken from the curve: they consume lots FIFO,
  reducing each lot's principal proportionally to the share of its gross value redeemed.
  Realized P/L is net of the regressive IOF/IR due on the redeemed yield and of fees.
- IR and IOF rates come from the tax rule registry (`domain.tax`), resolved by the date of
  the redemption (or of the valuation), so a legal change is a new rule record.
- The 12-month projection is the change in net value over the next 252 business days (or
  until maturity), including the drop of the regressive income tax bracket.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta

from core.helpers.calendar import business_days_between
from domain.portfolio.services.positions import InsufficientQuantityError
from domain.shared.entities import FixedIncomeTermEntity, TransactionEntity
from domain.shared.enums import (
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    TransactionKind,
)
from domain.tax.entities import TaxRegime, TaxRuleBook
from domain.tax.services.rules import DEFAULT_RULE_BOOK, income_tax_regime

LTN_FACE_VALUE = 1000.0
BUSINESS_DAYS_PER_YEAR = 252.0
PROJECTION_CALENDAR_DAYS = 365
DEFAULT_OVERSELL_TOLERANCE = 0.05


@dataclass(frozen=True)
class RateCurves:
    """Index curves (canonical fractions) and annual fallbacks used to accrue fixed income."""

    cdi_daily: Mapping[date, float] = field(default_factory=dict)
    selic_daily: Mapping[date, float] = field(default_factory=dict)
    ipca_monthly: Mapping[tuple[int, int], float] = field(default_factory=dict)
    annual_cdi_rate: float = 0.1075
    annual_ipca_rate: float = 0.045
    annual_selic_rate: float | None = None

    @property
    def selic_annual(self) -> float:
        return (
            self.annual_selic_rate if self.annual_selic_rate is not None else self.annual_cdi_rate
        )


@dataclass(frozen=True)
class FixedIncomeValuation:
    """Detailed valuation of a fixed income position as of a reference date."""

    invested_principal: float
    gross_value: float
    gross_yield: float
    gross_yield_pct: float
    iof_tax: float
    income_tax_rate: float
    income_tax: float
    net_value: float
    net_yield: float
    net_yield_pct: float
    projected_12m_net_yield: float
    realized_pnl: float = 0.0
    curve_coverage: float = 1.0


@dataclass
class FixedIncomeLot:
    """Open purchase lot: principal still invested and the date it started accruing."""

    start: date
    principal: float
    rate: float | None = None


@dataclass(frozen=True)
class _Accrual:
    factor: float
    business_days: int
    covered_days: int


def regressive_ir_rate(
    calendar_days: int,
    *,
    tax_exempt: bool = False,
    on: date | None = None,
    rules: TaxRuleBook | None = None,
) -> float:
    """Regressive income tax rate for a holding period, in force on `on` (default today)."""
    book = rules or DEFAULT_RULE_BOOK
    return book.rate(income_tax_regime(tax_exempt=tax_exempt), calendar_days, on or date.today())


def regressive_iof_rate(
    calendar_days: int,
    *,
    tax_exempt: bool = False,
    on: date | None = None,
    rules: TaxRuleBook | None = None,
) -> float:
    """Regressive IOF rate (applied before IR if redeemed in < 30 days)."""
    if tax_exempt or calendar_days <= 0:
        return 0.0
    book = rules or DEFAULT_RULE_BOOK
    return book.rate(TaxRegime.IOF_REGRESSIVE, calendar_days, on or date.today())


def implied_purchase_rate(
    term: FixedIncomeTermEntity, trade_date: date, unit_price: float
) -> float | None:
    """Annual rate implied by the price paid for a zero-coupon Tesouro Prefixado (LTN).

    Returns `None` for any other bond, or when the price cannot imply a sane rate.
    """
    if (
        term.instrument_kind != FixedIncomeInstrumentKind.TESOURO_PRE
        or term.semiannual_coupons
        or term.maturity_date is None
        or term.maturity_date <= trade_date
        or not 0.0 < unit_price < LTN_FACE_VALUE
    ):
        return None
    business_days = count_business_days(trade_date, term.maturity_date)
    if business_days <= 0:
        return None
    rate = (LTN_FACE_VALUE / unit_price) ** (BUSINESS_DAYS_PER_YEAR / business_days) - 1.0
    return round(rate, 8) if 0.0 < rate <= 1.0 else None


def count_business_days(start_date: date, end_date: date) -> int:
    """Count national business days in (start_date, end_date]."""
    return len(business_days_between(start_date, end_date))


def _daily_fallback(annual_rate: float) -> float:
    return (1.0 + annual_rate) ** (1.0 / BUSINESS_DAYS_PER_YEAR) - 1.0


def _accrue_daily_index(
    days: list[date],
    series: Mapping[date, float],
    secondary: Mapping[date, float],
    annual_fallback: float,
    multiplier: float,
) -> _Accrual:
    fallback = _daily_fallback(annual_fallback)
    factor = 1.0
    covered = 0
    for day in days:
        rate = series.get(day)
        if rate is None:
            rate = secondary.get(day)
        if rate is None:
            rate = fallback
        else:
            covered += 1
        factor *= 1.0 + rate * multiplier
    return _Accrual(factor, len(days), covered)


def _accrue_ipca(days: list[date], curves: RateCurves) -> _Accrual:
    monthly_fallback = (1.0 + curves.annual_ipca_rate) ** (1.0 / 12.0) - 1.0
    by_month: dict[tuple[int, int], int] = {}
    for day in days:
        key = (day.year, day.month)
        by_month[key] = by_month.get(key, 0) + 1

    factor = 1.0
    covered = 0
    for (year, month), window_days in by_month.items():
        first = date(year, month, 1)
        next_month = date(year + month // 12, month % 12 + 1, 1)
        month_days = count_business_days(first - timedelta(days=1), next_month - timedelta(1))
        rate = curves.ipca_monthly.get((year, month))
        if rate is None:
            rate = monthly_fallback
        else:
            covered += window_days
        factor *= (1.0 + rate) ** (window_days / month_days)
    return _Accrual(factor, len(days), covered)


def accrual_factor(
    term: FixedIncomeTermEntity,
    start: date,
    end: date,
    curves: RateCurves,
    *,
    rate: float | None = None,
) -> _Accrual:
    """Gross accrual factor of the contracted curve over business days in (start, end].

    `rate` overrides the contracted rate (a lot bought at its own rate).
    """
    if end <= start:
        return _Accrual(1.0, 0, 0)
    days = business_days_between(start, end)
    rate = float(term.contracted_rate) if rate is None else rate

    if term.indexer == FixedIncomeIndexer.CDI:
        return _accrue_daily_index(days, curves.cdi_daily, {}, curves.annual_cdi_rate, rate)
    if term.indexer == FixedIncomeIndexer.SELIC:
        return _accrue_daily_index(
            days, curves.selic_daily, curves.cdi_daily, curves.selic_annual, rate
        )

    real_factor = (1.0 + rate) ** (len(days) / BUSINESS_DAYS_PER_YEAR)
    if term.indexer == FixedIncomeIndexer.PRE:
        return _Accrual(real_factor, len(days), len(days))

    ipca = _accrue_ipca(days, curves)
    return _Accrual(ipca.factor * real_factor, ipca.business_days, ipca.covered_days)


def _projection_factor(
    term: FixedIncomeTermEntity,
    business_days: int,
    curves: RateCurves,
    rate: float | None = None,
) -> float:
    rate = float(term.contracted_rate) if rate is None else rate
    years = business_days / BUSINESS_DAYS_PER_YEAR
    if term.indexer == FixedIncomeIndexer.CDI:
        return (1.0 + _daily_fallback(curves.annual_cdi_rate) * rate) ** business_days
    if term.indexer == FixedIncomeIndexer.SELIC:
        return (1.0 + _daily_fallback(curves.selic_annual) * rate) ** business_days
    if term.indexer == FixedIncomeIndexer.PRE:
        return (1.0 + rate) ** years
    return ((1.0 + curves.annual_ipca_rate) * (1.0 + rate)) ** years


def _taxes(
    yield_brl: float,
    calendar_days: int,
    tax_exempt: bool,
    on: date,
    rules: TaxRuleBook,
) -> tuple[float, float]:
    taxable = max(0.0, yield_brl)
    iof = taxable * regressive_iof_rate(calendar_days, tax_exempt=tax_exempt, on=on, rules=rules)
    ir_rate = regressive_ir_rate(calendar_days, tax_exempt=tax_exempt, on=on, rules=rules)
    return iof, max(0.0, taxable - iof) * ir_rate


def redemption_taxes(
    yield_brl: float,
    calendar_days: int,
    *,
    tax_exempt: bool,
    on: date,
    rules: TaxRuleBook | None = None,
) -> tuple[float, float]:
    """IOF and IR due when a lot with `yield_brl` of gain is redeemed on `on`."""
    return _taxes(yield_brl, calendar_days, tax_exempt, on, rules or DEFAULT_RULE_BOOK)


def _redeem(
    lots: list[FixedIncomeLot],
    tx: TransactionEntity,
    term: FixedIncomeTermEntity,
    curves: RateCurves,
    tolerance: float,
    rules: TaxRuleBook,
) -> tuple[list[FixedIncomeLot], float]:
    on = tx.trade_date
    gross_redeemed = float(tx.quantity * tx.unit_price)
    lot_values = [
        lot.principal * accrual_factor(term, lot.start, on, curves, rate=lot.rate).factor
        for lot in lots
    ]
    position_value = sum(lot_values)
    if gross_redeemed > position_value * (1.0 + tolerance) + 0.01:
        raise InsufficientQuantityError(
            f"Redemption of {gross_redeemed:.2f} on {on} exceeds the position value "
            f"of {position_value:.2f}"
        )

    remaining = gross_redeemed
    realized = -float(tx.fees)
    kept: list[FixedIncomeLot] = []
    for index, (lot, lot_gross) in enumerate(zip(lots, lot_values, strict=True)):
        is_last = index == len(lots) - 1
        if remaining <= 0 or lot_gross <= 0:
            kept.append(lot)
            continue
        take = remaining if is_last and remaining > lot_gross else min(remaining, lot_gross)
        share = min(take / lot_gross, 1.0)
        consumed_principal = lot.principal * share
        iof, ir = _taxes(
            take - consumed_principal, (on - lot.start).days, term.tax_exempt, on, rules
        )
        realized += take - consumed_principal - iof - ir
        remaining -= take
        leftover = lot.principal - consumed_principal
        if leftover > 0.005:
            kept.append(FixedIncomeLot(lot.start, leftover, lot.rate))
    return kept, realized


def replay_lots(
    transactions: Iterable[TransactionEntity],
    term: FixedIncomeTermEntity,
    as_of_date: date,
    *,
    curves: RateCurves | None = None,
    oversell_tolerance: float = DEFAULT_OVERSELL_TOLERANCE,
    tax_rules: TaxRuleBook | None = None,
) -> tuple[list[FixedIncomeLot], float]:
    """Open FIFO lots on `as_of_date` and the realized P/L of the redemptions until then."""
    rates = curves or RateCurves()
    rules = tax_rules or DEFAULT_RULE_BOOK
    ordered = sorted(
        (t for t in transactions if t.trade_date <= as_of_date),
        key=lambda t: (t.trade_date, t.kind != TransactionKind.BUY, t.id or 0),
    )

    lots: list[FixedIncomeLot] = []
    realized = 0.0
    for tx in ordered:
        if tx.kind == TransactionKind.BUY:
            lots.append(
                FixedIncomeLot(
                    tx.trade_date,
                    float(tx.quantity * tx.unit_price + tx.fees),
                    implied_purchase_rate(term, tx.trade_date, float(tx.unit_price)),
                )
            )
        else:
            lots, trade_realized = _redeem(lots, tx, term, rates, oversell_tolerance, rules)
            realized += trade_realized
    return lots, realized


def valuation_end(term: FixedIncomeTermEntity, as_of_date: date) -> date:
    """Last accrual date: the valuation date, capped at maturity."""
    if term.maturity_date is not None:
        return min(as_of_date, term.maturity_date)
    return as_of_date


def projection_factor(
    term: FixedIncomeTermEntity,
    business_days: int,
    curves: RateCurves,
    *,
    rate: float | None = None,
) -> float:
    """Forward gross factor over `business_days` using the annual rates of `curves`."""
    return _projection_factor(term, business_days, curves, rate)


def value_fixed_income_position(
    transactions: Iterable[TransactionEntity],
    term: FixedIncomeTermEntity,
    as_of_date: date,
    *,
    curves: RateCurves | None = None,
    oversell_tolerance: float = DEFAULT_OVERSELL_TOLERANCE,
    tax_rules: TaxRuleBook | None = None,
) -> FixedIncomeValuation:
    """Compute accrued gross/net value, realized P/L and 12m projection of a fixed income asset.

    Raises `InsufficientQuantityError` when a redemption exceeds the position value by more
    than `oversell_tolerance` (relative), which callers treat as an invalid ledger.
    """
    rates = curves or RateCurves()
    rules = tax_rules or DEFAULT_RULE_BOOK
    lots, realized = replay_lots(
        transactions,
        term,
        as_of_date,
        curves=rates,
        oversell_tolerance=oversell_tolerance,
        tax_rules=rules,
    )

    if not lots:
        return FixedIncomeValuation(
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, round(realized, 2), 1.0
        )

    effective_end = valuation_end(term, as_of_date)
    # One standard year (252 business days) ahead, or less when the bond matures earlier.
    horizon_end = as_of_date + timedelta(days=PROJECTION_CALENDAR_DAYS)
    horizon_bd = int(BUSINESS_DAYS_PER_YEAR)
    if term.maturity_date is not None and term.maturity_date < horizon_end:
        horizon_end = term.maturity_date
        horizon_bd = count_business_days(effective_end, horizon_end)
    if horizon_end <= effective_end:
        horizon_bd = 0
    horizon_cal_days = max(0, (horizon_end - effective_end).days)

    invested_principal = gross_value = total_iof = total_ir = weighted_ir = 0.0
    net_at_horizon = 0.0
    covered_days = business_days = 0
    for lot in lots:
        accrual = accrual_factor(term, lot.start, effective_end, rates, rate=lot.rate)
        lot_gross = lot.principal * accrual.factor
        cal_days = max(0, (effective_end - lot.start).days)
        iof, ir = _taxes(lot_gross - lot.principal, cal_days, term.tax_exempt, effective_end, rules)

        invested_principal += lot.principal
        gross_value += lot_gross
        total_iof += iof
        total_ir += ir
        weighted_ir += lot.principal * regressive_ir_rate(
            cal_days, tax_exempt=term.tax_exempt, on=effective_end, rules=rules
        )
        covered_days += accrual.covered_days
        business_days += accrual.business_days

        lot_gross_h = lot_gross * _projection_factor(term, horizon_bd, rates, lot.rate)
        iof_h, ir_h = _taxes(
            lot_gross_h - lot.principal,
            cal_days + horizon_cal_days,
            term.tax_exempt,
            horizon_end,
            rules,
        )
        net_at_horizon += lot_gross_h - iof_h - ir_h

    gross_yield = gross_value - invested_principal
    net_value = gross_value - total_iof - total_ir
    net_yield = net_value - invested_principal

    def pct(value: float) -> float:
        return value / invested_principal * 100.0 if invested_principal > 0 else 0.0

    return FixedIncomeValuation(
        invested_principal=round(invested_principal, 2),
        gross_value=round(gross_value, 2),
        gross_yield=round(gross_yield, 2),
        gross_yield_pct=round(pct(gross_yield), 4),
        iof_tax=round(total_iof, 2),
        income_tax_rate=round(weighted_ir / invested_principal, 4) if invested_principal else 0.0,
        income_tax=round(total_ir, 2),
        net_value=round(net_value, 2),
        net_yield=round(net_yield, 2),
        net_yield_pct=round(pct(net_yield), 4),
        projected_12m_net_yield=round(net_at_horizon - net_value, 2) if horizon_bd else 0.0,
        realized_pnl=round(realized, 2),
        curve_coverage=round(covered_days / business_days, 4) if business_days else 1.0,
    )
