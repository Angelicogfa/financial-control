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
- Redemptions (SELL) are gross amounts taken from the curve: they consume lots FIFO,
  reducing each lot's principal proportionally to the share of its gross value redeemed.
  Realized P/L is net of the regressive IOF/IR due on the redeemed yield and of fees.
- The 12-month projection is the change in net value over the next 252 business days (or
  until maturity), including the drop of the regressive income tax bracket.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta

from fincontrol_core.calendar import business_days_between
from fincontrol_core.domain.entities import FixedIncomeTermEntity, TransactionEntity
from fincontrol_core.domain.enums import FixedIncomeIndexer, TransactionKind
from fincontrol_core.portfolio.positions import InsufficientQuantityError

BUSINESS_DAYS_PER_YEAR = 252.0
PROJECTION_CALENDAR_DAYS = 365
DEFAULT_OVERSELL_TOLERANCE = 0.05

# Official Brazilian IOF regressive table for redemptions between 1 and 29 calendar days
IOF_TABLE: tuple[float, ...] = (
    0.96, 0.93, 0.90, 0.86, 0.83, 0.80, 0.76, 0.73, 0.70, 0.66,
    0.63, 0.60, 0.56, 0.53, 0.50, 0.46, 0.43, 0.40, 0.36, 0.33,
    0.30, 0.26, 0.23, 0.20, 0.16, 0.13, 0.10, 0.06, 0.03,
)  # fmt: skip


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
class _Lot:
    start: date
    principal: float


@dataclass(frozen=True)
class _Accrual:
    factor: float
    business_days: int
    covered_days: int


def regressive_ir_rate(calendar_days: int, *, tax_exempt: bool = False) -> float:
    """Return the Brazilian regressive income tax rate based on holding calendar days."""
    if tax_exempt:
        return 0.0
    if calendar_days <= 180:
        return 0.225
    if calendar_days <= 360:
        return 0.200
    if calendar_days <= 720:
        return 0.175
    return 0.150


def regressive_iof_rate(calendar_days: int, *, tax_exempt: bool = False) -> float:
    """Return the regressive IOF rate (applied before IR if redeemed in < 30 days)."""
    if tax_exempt or calendar_days <= 0 or calendar_days >= 30:
        return 0.0
    return IOF_TABLE[calendar_days - 1]


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
    term: FixedIncomeTermEntity, start: date, end: date, curves: RateCurves
) -> _Accrual:
    """Gross accrual factor of the contracted curve over business days in (start, end]."""
    if end <= start:
        return _Accrual(1.0, 0, 0)
    days = business_days_between(start, end)
    rate = float(term.contracted_rate)

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
    term: FixedIncomeTermEntity, business_days: int, curves: RateCurves
) -> float:
    rate = float(term.contracted_rate)
    years = business_days / BUSINESS_DAYS_PER_YEAR
    if term.indexer == FixedIncomeIndexer.CDI:
        return (1.0 + _daily_fallback(curves.annual_cdi_rate) * rate) ** business_days
    if term.indexer == FixedIncomeIndexer.SELIC:
        return (1.0 + _daily_fallback(curves.selic_annual) * rate) ** business_days
    if term.indexer == FixedIncomeIndexer.PRE:
        return (1.0 + rate) ** years
    return ((1.0 + curves.annual_ipca_rate) * (1.0 + rate)) ** years


def _taxes(yield_brl: float, calendar_days: int, tax_exempt: bool) -> tuple[float, float]:
    taxable = max(0.0, yield_brl)
    iof = taxable * regressive_iof_rate(calendar_days, tax_exempt=tax_exempt)
    ir = max(0.0, taxable - iof) * regressive_ir_rate(calendar_days, tax_exempt=tax_exempt)
    return iof, ir


def _redeem(
    lots: list[_Lot],
    tx: TransactionEntity,
    term: FixedIncomeTermEntity,
    curves: RateCurves,
    tolerance: float,
) -> tuple[list[_Lot], float]:
    on = tx.trade_date
    gross_redeemed = float(tx.quantity * tx.unit_price)
    lot_values = [
        lot.principal * accrual_factor(term, lot.start, on, curves).factor for lot in lots
    ]
    position_value = sum(lot_values)
    if gross_redeemed > position_value * (1.0 + tolerance) + 0.01:
        raise InsufficientQuantityError(
            f"Redemption of {gross_redeemed:.2f} on {on} exceeds the position value "
            f"of {position_value:.2f}"
        )

    remaining = gross_redeemed
    realized = -float(tx.fees)
    kept: list[_Lot] = []
    for index, (lot, lot_gross) in enumerate(zip(lots, lot_values, strict=True)):
        is_last = index == len(lots) - 1
        if remaining <= 0 or lot_gross <= 0:
            kept.append(lot)
            continue
        take = remaining if is_last and remaining > lot_gross else min(remaining, lot_gross)
        share = min(take / lot_gross, 1.0)
        consumed_principal = lot.principal * share
        iof, ir = _taxes(take - consumed_principal, (on - lot.start).days, term.tax_exempt)
        realized += take - consumed_principal - iof - ir
        remaining -= take
        leftover = lot.principal - consumed_principal
        if leftover > 0.005:
            kept.append(_Lot(lot.start, leftover))
    return kept, realized


def value_fixed_income_position(
    transactions: Iterable[TransactionEntity],
    term: FixedIncomeTermEntity,
    as_of_date: date,
    *,
    curves: RateCurves | None = None,
    oversell_tolerance: float = DEFAULT_OVERSELL_TOLERANCE,
) -> FixedIncomeValuation:
    """Compute accrued gross/net value, realized P/L and 12m projection of a fixed income asset.

    Raises `InsufficientQuantityError` when a redemption exceeds the position value by more
    than `oversell_tolerance` (relative), which callers treat as an invalid ledger.
    """
    rates = curves or RateCurves()
    ordered = sorted(
        (t for t in transactions if t.trade_date <= as_of_date),
        key=lambda t: (t.trade_date, t.kind != TransactionKind.BUY, t.id or 0),
    )

    lots: list[_Lot] = []
    realized = 0.0
    for tx in ordered:
        if tx.kind == TransactionKind.BUY:
            lots.append(
                _Lot(
                    max(tx.trade_date, term.issue_date),
                    float(tx.quantity * tx.unit_price + tx.fees),
                )
            )
        else:
            lots, trade_realized = _redeem(lots, tx, term, rates, oversell_tolerance)
            realized += trade_realized

    if not lots:
        return FixedIncomeValuation(
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, round(realized, 2), 1.0
        )

    effective_end = (
        min(as_of_date, term.maturity_date) if term.maturity_date is not None else as_of_date
    )
    # One standard year (252 business days) ahead, or less when the bond matures earlier.
    horizon_end = as_of_date + timedelta(days=PROJECTION_CALENDAR_DAYS)
    horizon_bd = int(BUSINESS_DAYS_PER_YEAR)
    if term.maturity_date is not None and term.maturity_date < horizon_end:
        horizon_end = term.maturity_date
        horizon_bd = count_business_days(effective_end, horizon_end)
    if horizon_end <= effective_end:
        horizon_bd = 0
    horizon_cal_days = max(0, (horizon_end - effective_end).days)
    projection_factor = _projection_factor(term, horizon_bd, rates)

    invested_principal = gross_value = total_iof = total_ir = weighted_ir = 0.0
    net_at_horizon = 0.0
    covered_days = business_days = 0
    for lot in lots:
        accrual = accrual_factor(term, lot.start, effective_end, rates)
        lot_gross = lot.principal * accrual.factor
        cal_days = max(0, (effective_end - lot.start).days)
        iof, ir = _taxes(lot_gross - lot.principal, cal_days, term.tax_exempt)

        invested_principal += lot.principal
        gross_value += lot_gross
        total_iof += iof
        total_ir += ir
        weighted_ir += lot.principal * regressive_ir_rate(cal_days, tax_exempt=term.tax_exempt)
        covered_days += accrual.covered_days
        business_days += accrual.business_days

        lot_gross_h = lot_gross * projection_factor
        iof_h, ir_h = _taxes(
            lot_gross_h - lot.principal, cal_days + horizon_cal_days, term.tax_exempt
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
