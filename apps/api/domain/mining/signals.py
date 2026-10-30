"""Point-in-time signals of the Garimpo (Phase 43.2).

Every month, with only what was known that month (statements by their delivery date, prices up
to the month), each company gets four signals, each a z against its sector (the sector centre
pulled to the market, as in the valuation layer) and winsorised to ±3:

- VALUE: the valuation z of Phase 42.3 (earnings, book, EBITDA/EV and dividend yields against
  the company's own past and its sector).
- QUALITY: return on equity, net margin, low leverage (net debt / EBITDA) and the stability of
  the return on equity over the last two years of deliveries.
- IMPROVEMENT: how much the 12-month net income grew over the year, scaled by equity (works
  for losses), and how much the net margin moved.
- MOMENTUM: the return over the class in the 12 months before the last one (12-1), the price
  signal with the most evidence (Jegadeesh-Titman); the last month is left out because it
  tends to reverse.

Banks and insurers have no revenue, EBITDA or debt in the company sense: their quality is the
return on equity and its stability, their improvement the income growth.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date

import numpy as np

from domain.disclosures.statements import COMPANY, NET_INCOME, REVENUE, PitFundamentals
from domain.forecast.valuation_model import (
    MAX_STATEMENT_AGE_DAYS,
    WINSOR,
    CompanyInput,
    Month,
    add_months,
    company_yields,
    month_end,
    sector_z,
    value_scores,
)

VALUE = "VALUE"
QUALITY = "QUALITY"
IMPROVEMENT = "IMPROVEMENT"
MOMENTUM = "MOMENTUM"
SIGNALS = (VALUE, QUALITY, IMPROVEMENT, MOMENTUM)

STABILITY_DELIVERIES = 8  # two years of quarterly deliveries
MIN_STABILITY_DELIVERIES = 4
MOMENTUM_MONTHS = 11  # months t-11 .. t-1
YEAR_TOLERANCE_DAYS = 45


def _known(company: CompanyInput, month: Month) -> tuple[int, PitFundamentals] | None:
    delivered = [s.delivered_on for s in company.snapshots]
    end = month_end(month)
    i = bisect.bisect_right(delivered, end) - 1
    if i < 0:
        return None
    snap = company.snapshots[i]
    if (end - snap.reference_date).days > MAX_STATEMENT_AGE_DAYS:
        return None
    return i, snap


def _roe(snap: PitFundamentals) -> float | None:
    income, equity = snap.get(NET_INCOME), snap.controlling_equity
    return income / equity if income is not None and equity and equity > 0 else None


def _margin(snap: PitFundamentals) -> float | None:
    income, revenue = snap.get(NET_INCOME), snap.get(REVENUE)
    return income / revenue if income is not None and revenue and revenue > 0 else None


def _year_before(company: CompanyInput, index: int) -> PitFundamentals | None:
    """The snapshot whose reference date is about one year before the one at `index`."""
    target = company.snapshots[index].reference_date
    for snap in reversed(company.snapshots[:index]):
        if abs((target - snap.reference_date).days - 365) <= YEAR_TOLERANCE_DAYS:
            return snap
    return None


def fundamentals_raw(company: CompanyInput, month: Month) -> dict[str, float]:
    """Raw quality and improvement measures of one month (missing ones are left out)."""
    found = _known(company, month)
    if found is None:
        return {}
    index, snap = found
    out: dict[str, float] = {}
    roe, margin = _roe(snap), _margin(snap)
    if roe is not None:
        out["roe"] = roe
    if snap.template == COMPANY:
        if margin is not None:
            out["margin"] = margin
        ebitda, net_debt = snap.ebitda, snap.net_debt
        if ebitda and ebitda > 0 and net_debt is not None:
            out["low_leverage"] = -net_debt / ebitda
    # One snapshot per reference date (the newest version) for the stability window.
    by_reference = {s.reference_date: s for s in company.snapshots[: index + 1]}
    recent = [by_reference[r] for r in sorted(by_reference)[-STABILITY_DELIVERIES:]]
    roes = [r for s in recent if (r := _roe(s)) is not None]
    if len(roes) >= MIN_STABILITY_DELIVERIES:
        out["roe_stability"] = -float(np.std(roes, ddof=1))
    before = _year_before(company, index)
    if before is not None:
        income_now, income_then = snap.get(NET_INCOME), before.get(NET_INCOME)
        equity = snap.controlling_equity
        if income_now is not None and income_then is not None and equity and equity > 0:
            out["income_growth"] = (income_now - income_then) / equity
        if snap.template == COMPANY:
            then = _margin(before)
            if margin is not None and then is not None:
                out["margin_change"] = margin - then
    return out


QUALITY_PARTS = ("roe", "margin", "low_leverage", "roe_stability")
IMPROVEMENT_PARTS = ("income_growth", "margin_change")


def momentum_raw(alphas: Mapping[Month, float], month: Month) -> float | None:
    """Sum of the monthly returns over the class from t-11 to t-1 (all 11 needed)."""
    values = [alphas.get(add_months(month, -k)) for k in range(1, MOMENTUM_MONTHS + 1)]
    if any(v is None for v in values):
        return None
    return float(sum(values))  # type: ignore[arg-type]


def _family_scores(
    raw: Mapping[str, Mapping[Month, Mapping[str, float]]],
    parts: Sequence[str],
    sectors: Mapping[str, str],
) -> dict[str, dict[Month, float]]:
    """Average of the sector z of each part, per company and month."""
    months = sorted({m for by_month in raw.values() for m in by_month})
    collected: dict[str, dict[Month, list[float]]] = defaultdict(lambda: defaultdict(list))
    for month in months:
        for part in parts:
            row = {
                t: by_month[month][part]
                for t, by_month in raw.items()
                if month in by_month and part in by_month[month]
            }
            for t, z in sector_z(row, sectors).items():
                collected[t][month].append(z)
    return {
        t: {m: float(np.clip(np.mean(zs), -WINSOR, WINSOR)) for m, zs in by_month.items() if zs}
        for t, by_month in collected.items()
    }


def mining_signals(
    companies: Mapping[str, CompanyInput],
    alphas: Mapping[str, Mapping[Month, float]],
    months: Sequence[Month],
) -> dict[str, dict[Month, dict[str, float]]]:
    """The four signals of each company and month (a signal may be missing)."""
    sectors = {t: c.sector for t, c in companies.items()}
    value = value_scores({t: company_yields(c) for t, c in companies.items()}, sectors)
    raw = {t: {m: fundamentals_raw(c, m) for m in months} for t, c in companies.items()}
    quality = _family_scores(raw, QUALITY_PARTS, sectors)
    improvement = _family_scores(raw, IMPROVEMENT_PARTS, sectors)
    momentum_rows = {
        t: {
            m: {"momentum": v}
            for m in months
            if (v := momentum_raw(alphas.get(t, {}), m)) is not None
        }
        for t in companies
    }
    momentum = _family_scores(momentum_rows, ("momentum",), sectors)

    out: dict[str, dict[Month, dict[str, float]]] = defaultdict(dict)
    for name, family in (
        (VALUE, value),
        (QUALITY, quality),
        (IMPROVEMENT, improvement),
        (MOMENTUM, momentum),
    ):
        for t, by_month in family.items():
            for m, z in by_month.items():
                out[t].setdefault(m, {})[name] = round(z, 4)
    return dict(out)


def month_list(start: Month, end: date) -> list[Month]:
    out, month = [], start
    while month_end(month) <= end:
        out.append(month)
        month = add_months(month, 1)
    return out
