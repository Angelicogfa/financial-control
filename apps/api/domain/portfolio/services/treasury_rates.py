"""Rates implied by the unit price paid for Tesouro Direto bonds (LTN, NTN-F, NTN-B).

Conventions (ANBIMA pricing, simplified: no truncation of intermediate figures):
- Discounting is exponential over business days: v = (1 + r) ^ (-du / 252), with `du`
  counted by the national holiday calendar from the trade date (exclusive) to each flow.
- LTN (Tesouro Prefixado): PU = 1000 * v(maturity).
- NTN-F (Prefixado com Juros Semestrais): 10% a.a. coupons, (1.10 ^ 0.5 - 1) of 1000 every
  six months back from maturity, plus 1000 at maturity.
- NTN-B Principal (Tesouro IPCA+): PU = VNA * v(maturity).
- NTN-B (IPCA+ com Juros Semestrais): PU = VNA * (sum of 6% a.a. coupons + 1, discounted).
- VNA (valor nominal atualizado) is 1000 on 2000-07-15, updated on the 15th of each month by
  the IPCA of the previous month; between two 15ths it grows pro-rata by business days with
  the IPCA of the month of the last 15th (projected from the annual fallback while the month
  is not published). A gap inside the published IPCA history makes the VNA unknown.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from core.helpers.calendar import business_days_between
from domain.shared.entities import FixedIncomeTermEntity
from domain.shared.enums import FixedIncomeInstrumentKind

FACE_VALUE = 1000.0
VNA_BASE_DATE = date(2000, 7, 15)
VNA_BASE_VALUE = 1000.0
IPCA_HISTORY_START = date(2000, 7, 1)
NTNF_COUPON = 1.10**0.5 - 1.0
NTNB_COUPON = 1.06**0.5 - 1.0
MAX_IMPLIED_RATE = 0.5
_BUSINESS_DAYS_PER_YEAR = 252.0
_SOLVER_ITERATIONS = 200
_SOLVER_TOLERANCE = 1e-12


def _business_days(start: date, end: date) -> int:
    return len(business_days_between(start, end))


def _shift_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, day.day)


def _months(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    """Months from `start` to `end`, both inclusive."""
    first, last = start[0] * 12 + start[1] - 1, end[0] * 12 + end[1] - 1
    return [(i // 12, i % 12 + 1) for i in range(first, last + 1)]


def _monthly_fallback(annual_ipca_rate: float) -> float:
    return (1.0 + annual_ipca_rate) ** (1.0 / 12.0) - 1.0


def vna_on(
    day: date, ipca_monthly: Mapping[tuple[int, int], float], annual_ipca_rate: float
) -> float | None:
    """NTN-B updated nominal value on `day`, or `None` when the IPCA history is incomplete."""
    if day < VNA_BASE_DATE or not ipca_monthly:
        return None
    base_month = (VNA_BASE_DATE.year, VNA_BASE_DATE.month)
    latest = max(ipca_monthly)
    if any(m not in ipca_monthly for m in _months(base_month, latest)):
        return None

    fallback = _monthly_fallback(annual_ipca_rate)
    last_15th = (
        date(day.year, day.month, 15)
        if day.day >= 15
        else _shift_months(date(day.year, day.month, 15), -1)
    )
    vna = VNA_BASE_VALUE
    previous_month = _shift_months(last_15th, -1)
    if last_15th > VNA_BASE_DATE:
        for month in _months(base_month, (previous_month.year, previous_month.month)):
            vna *= 1.0 + ipca_monthly.get(month, fallback)

    next_15th = _shift_months(last_15th, 1)
    elapsed = _business_days(last_15th, day)
    if elapsed:
        rate = ipca_monthly.get((last_15th.year, last_15th.month), fallback)
        vna *= (1.0 + rate) ** (elapsed / _business_days(last_15th, next_15th))
    return vna


def _flows(
    trade_date: date, maturity: date, coupon: float, principal: float
) -> list[tuple[int, float]]:
    """(business days from the trade date, amount) of each remaining cash flow."""
    flows = [(maturity, principal * (1.0 + coupon))]
    if coupon:
        step = 1
        while (paid := _shift_months(maturity, -6 * step)) > trade_date:
            flows.append((paid, principal * coupon))
            step += 1
    return [(_business_days(trade_date, when), amount) for when, amount in flows]


def _present_value(flows: list[tuple[int, float]], rate: float) -> float:
    return sum(amount / (1.0 + rate) ** (du / _BUSINESS_DAYS_PER_YEAR) for du, amount in flows)


def _solve_rate(flows: list[tuple[int, float]], price: float) -> float | None:
    """Annual rate in (0, MAX_IMPLIED_RATE] whose present value of `flows` equals `price`."""
    if len(flows) == 1:
        du, amount = flows[0]
        if du <= 0 or price <= 0:
            return None
        rate = (amount / price) ** (_BUSINESS_DAYS_PER_YEAR / du) - 1.0
        return rate if 0.0 < rate <= MAX_IMPLIED_RATE else None
    low, high = 0.0, MAX_IMPLIED_RATE
    if not _present_value(flows, high) <= price < _present_value(flows, low):
        return None
    for _ in range(_SOLVER_ITERATIONS):
        middle = (low + high) / 2.0
        if _present_value(flows, middle) > price:
            low = middle
        else:
            high = middle
        if high - low < _SOLVER_TOLERANCE:
            break
    return (low + high) / 2.0


def implied_purchase_rate(
    term: FixedIncomeTermEntity,
    trade_date: date,
    unit_price: float,
    *,
    ipca_monthly: Mapping[tuple[int, int], float] | None = None,
    annual_ipca_rate: float = 0.045,
) -> float | None:
    """Annual rate (nominal for Prefixado, real over IPCA for IPCA+) implied by the PU paid.

    Returns `None` for Tesouro Selic and bank securities, when the bond has no maturity, when
    the IPCA history needed for the VNA is incomplete, or when no sane rate fits the price.
    """
    maturity = term.maturity_date
    if maturity is None or maturity <= trade_date or unit_price <= 0:
        return None
    if term.instrument_kind == FixedIncomeInstrumentKind.TESOURO_PRE:
        coupon = NTNF_COUPON if term.semiannual_coupons else 0.0
        rate = _solve_rate(_flows(trade_date, maturity, coupon, FACE_VALUE), unit_price)
    elif term.instrument_kind == FixedIncomeInstrumentKind.TESOURO_IPCA:
        vna = vna_on(trade_date, ipca_monthly or {}, annual_ipca_rate)
        if vna is None:
            return None
        coupon = NTNB_COUPON if term.semiannual_coupons else 0.0
        rate = _solve_rate(_flows(trade_date, maturity, coupon, 1.0), unit_price / vna)
    else:
        return None
    return round(rate, 8) if rate is not None else None
