"""Signals the recommendation adds to the point-in-time panel (Phase 45.1).

The Garimpo's monthly panel (`mining_signals`: VALUE, QUALITY, IMPROVEMENT, MOMENTUM) is the one
register of point-in-time signals; the recommendation's lenses read it, and these two families
join it, computed in the same weekly run on the same companies and with the same rule (a z
against the sector, the sector centre pulled to the market, winsorised to ±3):

- INCOME: the trailing dividend yield of the statements delivered by then, and how regularly the
  company paid (share of the last five years of deliveries with dividends in the trailing year).
- RISK: low volatility and low drawdown of the monthly returns over the CDI in the last 36
  months (the sign is flipped, so a high z is a low risk).

The Garimpo's own model keeps only its four signals.
"""

from __future__ import annotations

import bisect
from collections.abc import Mapping, Sequence

import numpy as np

from domain.disclosures.statements import DIVIDENDS_PAID
from domain.forecast.valuation_model import (
    CompanyInput,
    Month,
    add_months,
    company_yields,
    month_end,
)
from domain.mining.signals import SIGNALS, family_scores

INCOME = "INCOME"
RISK = "RISK"
EXTRA_SIGNALS = (INCOME, RISK)
REGISTRY_SIGNALS = (*SIGNALS, *EXTRA_SIGNALS)

REGULARITY_YEARS = 5
MIN_REGULARITY_DELIVERIES = 8  # two years of quarterly deliveries
RISK_MONTHS = 36
MIN_RISK_MONTHS = 24

INCOME_PARTS = ("dividend_yield", "regularity")
RISK_PARTS = ("low_volatility", "low_drawdown")


def regularity(company: CompanyInput, month: Month) -> float | None:
    """Share of the deliveries of the last five years with dividends paid in the trailing year."""
    delivered = [s.delivered_on for s in company.snapshots]
    end = month_end(month)
    i = bisect.bisect_right(delivered, end) - 1
    if i < 0:
        return None
    start = month_end(add_months(month, -12 * REGULARITY_YEARS))
    # One snapshot per reference date (the newest version known by then).
    by_reference = {s.reference_date: s for s in company.snapshots[: i + 1]}
    window = [s for r, s in by_reference.items() if r > start]
    if len(window) < MIN_REGULARITY_DELIVERIES:
        return None
    paid = sum(1 for s in window if (s.get(DIVIDENDS_PAID) or 0.0) > 0)
    return paid / len(window)


def risk_raw(excess: Mapping[Month, float], month: Month) -> dict[str, float]:
    """Low volatility and low drawdown of the monthly returns up to `month` (signs flipped)."""
    values = [v for k in range(RISK_MONTHS) if (v := excess.get(add_months(month, -k))) is not None]
    if len(values) < MIN_RISK_MONTHS:
        return {}
    returns = np.array(list(reversed(values)))
    wealth = np.cumprod(1.0 + returns)
    drawdown = float(np.max(1.0 - wealth / np.maximum.accumulate(wealth)))
    volatility = float(np.std(returns, ddof=1) * np.sqrt(12.0))
    return {"low_volatility": -volatility, "low_drawdown": -drawdown}


def registry_signals(
    companies: Mapping[str, CompanyInput],
    excess: Mapping[str, Mapping[Month, float]],
    months: Sequence[Month],
) -> dict[str, dict[Month, dict[str, float]]]:
    """INCOME and RISK of each company and month (a signal may be missing)."""
    sectors = {t: c.sector for t, c in companies.items()}
    income_raw: dict[str, dict[Month, dict[str, float]]] = {}
    for ticker, company in companies.items():
        yields = company_yields(company)
        rows: dict[Month, dict[str, float]] = {}
        for month in months:
            row = {}
            dy = yields.get(month, {}).get("dividend_yield")
            if dy is not None:
                row["dividend_yield"] = dy
            share = regularity(company, month)
            if share is not None:
                row["regularity"] = share
            if row:
                rows[month] = row
        income_raw[ticker] = rows
    risk = {
        t: {m: row for m in months if (row := risk_raw(excess.get(t, {}), m))} for t in companies
    }
    out: dict[str, dict[Month, dict[str, float]]] = {}
    for name, family in (
        (INCOME, family_scores(income_raw, INCOME_PARTS, sectors)),
        (RISK, family_scores(risk, RISK_PARTS, sectors)),
    ):
        for t, by_month in family.items():
            for m, z in by_month.items():
                out.setdefault(t, {}).setdefault(m, {})[name] = round(z, 4)
    return out
