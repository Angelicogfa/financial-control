"""Automatic fixed income valuation along contracted indexer curves (CDI, SELIC, IPCA+, Pre).

Computes gross accrued value, regressive IOF (days 1-29), regressive Brazilian income tax
(22.5%, 20.0%, 17.5%, 15.0% — or 0% for tax-exempt instruments like LCI/LCA/CRI/CRA),
net current value, and 12-month forward projection.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from fincontrol_core.domain.entities import FixedIncomeTermEntity, TransactionEntity
from fincontrol_core.domain.enums import FixedIncomeIndexer, TransactionKind

BUSINESS_DAYS_PER_YEAR = 252.0

# Official Brazilian IOF regressive table for redemptions between 1 and 29 calendar days
IOF_TABLE: tuple[float, ...] = (
    0.96, 0.93, 0.90, 0.86, 0.83, 0.80, 0.76, 0.73, 0.70, 0.66,
    0.63, 0.60, 0.56, 0.53, 0.50, 0.46, 0.43, 0.40, 0.36, 0.33,
    0.30, 0.26, 0.23, 0.20, 0.16, 0.13, 0.10, 0.06, 0.03,
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
    """Count weekday business days in (start_date, end_date]."""
    if end_date <= start_date:
        return 0
    total_days = (end_date - start_date).days
    full_weeks, extra_days = divmod(total_days, 7)
    business_days = full_weeks * 5
    current = start_date + timedelta(days=full_weeks * 7)
    for _ in range(extra_days):
        current += timedelta(days=1)
        if current.weekday() < 5:
            business_days += 1
    return business_days


def _compound_factor(
    term: FixedIncomeTermEntity,
    start_date: date,
    end_date: date,
    *,
    annual_cdi_rate: float,
    annual_ipca_rate: float,
    daily_cdi_series: Mapping[date, float] | None = None,
) -> float:
    if end_date <= start_date:
        return 1.0

    rate = float(term.contracted_rate)
    # Normalize percentage inputs (e.g. 110 -> 1.10 for CDI, or 12.5 -> 0.125)
    if term.indexer in (FixedIncomeIndexer.CDI, FixedIncomeIndexer.SELIC):
        multiplier = rate / 100.0 if rate > 5.0 else rate
        if daily_cdi_series:
            relevant = [
                d_rate
                for d_date, d_rate in daily_cdi_series.items()
                if start_date < d_date <= end_date
            ]
            if relevant:
                factor = 1.0
                for daily_pct in relevant:
                    daily_frac = daily_pct / 100.0 if abs(daily_pct) > 0.05 else daily_pct
                    factor *= 1.0 + daily_frac * multiplier
                return factor
        b_days = count_business_days(start_date, end_date)
        daily_cdi = (1.0 + annual_cdi_rate) ** (1.0 / BUSINESS_DAYS_PER_YEAR) - 1.0
        return (1.0 + daily_cdi * multiplier) ** b_days

    b_days = count_business_days(start_date, end_date)
    years = b_days / BUSINESS_DAYS_PER_YEAR
    spread = rate / 100.0 if rate > 1.0 else rate

    if term.indexer == FixedIncomeIndexer.PRE:
        return (1.0 + spread) ** years

    # IPCA + contracted real rate: (1 + IPCA) * (1 + real_rate)
    effective_annual = (1.0 + annual_ipca_rate) * (1.0 + spread) - 1.0
    return (1.0 + effective_annual) ** years


def value_fixed_income_position(
    transactions: Iterable[TransactionEntity],
    term: FixedIncomeTermEntity,
    as_of_date: date,
    *,
    annual_cdi_rate: float = 0.1075,
    annual_ipca_rate: float = 0.045,
    daily_cdi_series: Mapping[date, float] | None = None,
) -> FixedIncomeValuation:
    """Compute the accrued gross/net value and 12m projection for a fixed income asset."""
    ordered = sorted(transactions, key=lambda t: (t.trade_date, t.id or 0))
    # Track remaining principal lots FIFO to respect holding period taxes per lot
    lots: list[tuple[date, float]] = []

    for tx in ordered:
        if tx.trade_date > as_of_date:
            continue
        tx_value = float(tx.quantity * tx.unit_price + tx.fees)
        if tx.kind == TransactionKind.BUY:
            lots.append((tx.trade_date, tx_value))
        else:
            sell_remaining = float(tx.quantity * tx.unit_price)
            updated_lots: list[tuple[date, float]] = []
            for lot_date, lot_principal in lots:
                if sell_remaining <= 0:
                    updated_lots.append((lot_date, lot_principal))
                elif sell_remaining >= lot_principal:
                    sell_remaining -= lot_principal
                else:
                    updated_lots.append((lot_date, lot_principal - sell_remaining))
                    sell_remaining = 0.0
            lots = updated_lots

    if not lots:
        return FixedIncomeValuation(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    invested_principal = 0.0
    gross_value = 0.0
    total_iof = 0.0
    total_ir = 0.0
    weighted_ir_num = 0.0

    effective_end = (
        min(as_of_date, term.maturity_date)
        if term.maturity_date is not None
        else as_of_date
    )

    for lot_date, principal in lots:
        start = max(lot_date, term.issue_date)
        factor = _compound_factor(
            term,
            start,
            effective_end,
            annual_cdi_rate=annual_cdi_rate,
            annual_ipca_rate=annual_ipca_rate,
            daily_cdi_series=daily_cdi_series,
        )
        lot_gross = principal * factor
        lot_yield = max(0.0, lot_gross - principal)
        cal_days = max(0, (effective_end - start).days)

        iof_rate = regressive_iof_rate(cal_days, tax_exempt=term.tax_exempt)
        lot_iof = lot_yield * iof_rate
        taxable_after_iof = max(0.0, lot_yield - lot_iof)

        ir_rate = regressive_ir_rate(cal_days, tax_exempt=term.tax_exempt)
        lot_ir = taxable_after_iof * ir_rate

        invested_principal += principal
        gross_value += lot_gross
        total_iof += lot_iof
        total_ir += lot_ir
        weighted_ir_num += principal * ir_rate

    gross_yield = gross_value - invested_principal
    gross_yield_pct = (gross_yield / invested_principal * 100.0) if invested_principal > 0 else 0.0
    net_value = gross_value - total_iof - total_ir
    net_yield = net_value - invested_principal
    net_yield_pct = (net_yield / invested_principal * 100.0) if invested_principal > 0 else 0.0
    avg_ir_rate = weighted_ir_num / invested_principal if invested_principal > 0 else 0.0

    # 12-month forward projection on current net value
    future_start = date(2026, 1, 1)
    future_end = date(2027, 1, 1)
    one_year_gross_factor = _compound_factor(
        term,
        future_start,
        future_end,
        annual_cdi_rate=annual_cdi_rate,
        annual_ipca_rate=annual_ipca_rate,
        daily_cdi_series=None,
    )
    projected_gross_gain = net_value * (one_year_gross_factor - 1.0)
    long_term_ir = 0.0 if term.tax_exempt else 0.15
    projected_12m_net_yield = projected_gross_gain * (1.0 - long_term_ir)

    return FixedIncomeValuation(
        invested_principal=round(invested_principal, 2),
        gross_value=round(gross_value, 2),
        gross_yield=round(gross_yield, 2),
        gross_yield_pct=round(gross_yield_pct, 4),
        iof_tax=round(total_iof, 2),
        income_tax_rate=round(avg_ir_rate, 4),
        income_tax=round(total_ir, 2),
        net_value=round(net_value, 2),
        net_yield=round(net_yield, 2),
        net_yield_pct=round(net_yield_pct, 4),
        projected_12m_net_yield=round(projected_12m_net_yield, 2),
    )
