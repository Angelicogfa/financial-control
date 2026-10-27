"""Generate golden expected values for the reference portfolio from first principles.

This script is the auditable "spreadsheet" behind `reference_portfolio_expected.csv`.
It deliberately uses only the standard library and never imports `fincontrol_core`, so
the expected values are an independent computation of the financial rules:

- Variable income: weighted average cost with fees added to cost; sell fees reduce realized
  P/L. Cost is converted with each purchase's FX, proceeds with each sale's FX and the open
  position with the current FX (ADR 0006 / finding C-02).
- CDI / SELIC: product of (1 + daily_pct / 100 * multiplier) over every business day in
  (purchase, as_of]. The BCB SGS 12 value is always a percentage (finding C-01).
- IPCA+: monthly IPCA applied pro-rata by business days inside each month,
  prod (1 + ipca_m)^(du_window_m / du_month_m), times (1 + real_rate)^(du_total / 252).
  Convention of this fixture: the current month's IPCA is treated as already known.
- Taxes: regressive IOF for < 30 calendar days, then regressive income tax
  (22.5% / 20% / 17.5% / 15%) on the yield net of IOF; exempt instruments pay neither.
- Business days: weekdays that are not in the fixture's holiday list.
- Rounding: every reported monetary value is rounded to cents; derived values
  (unrealized, consolidated, totals) are computed from the rounded components.

Usage: python build_reference_golden.py  (rewrites reference_portfolio_expected.csv)
"""

from __future__ import annotations

import csv
import json
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUT = HERE / "reference_portfolio.json"
OUTPUT = HERE / "reference_portfolio_expected.csv"

IOF_TABLE = (
    0.96, 0.93, 0.90, 0.86, 0.83, 0.80, 0.76, 0.73, 0.70, 0.66,
    0.63, 0.60, 0.56, 0.53, 0.50, 0.46, 0.43, 0.40, 0.36, 0.33,
    0.30, 0.26, 0.23, 0.20, 0.16, 0.13, 0.10, 0.06, 0.03,
)  # fmt: skip

# Rows the current implementation is known to get wrong, keyed by (ticker, metric).
KNOWN_FINDINGS: dict[tuple[str, str], str] = {}


def _d(raw: str) -> date:
    return date.fromisoformat(raw)


def _cents(value: float) -> float:
    return round(value + 0.0, 2)


class Calendar:
    def __init__(self, holidays: list[str]) -> None:
        self.holidays = {_d(h) for h in holidays}

    def is_business_day(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self.holidays

    def business_days(self, start: date, end: date) -> list[date]:
        """Business days in the half-open interval (start, end]."""
        days = []
        current = start + timedelta(days=1)
        while current <= end:
            if self.is_business_day(current):
                days.append(current)
            current += timedelta(days=1)
        return days


def ir_rate(calendar_days: int) -> float:
    if calendar_days <= 180:
        return 0.225
    if calendar_days <= 360:
        return 0.200
    if calendar_days <= 720:
        return 0.175
    return 0.150


def iof_rate(calendar_days: int) -> float:
    if calendar_days <= 0 or calendar_days >= 30:
        return 0.0
    return IOF_TABLE[calendar_days - 1]


def cdi_factor(cal: Calendar, cdi_by_month: dict, start: date, end: date, mult: float) -> float:
    factor = 1.0
    for day in cal.business_days(start, end):
        daily_pct = cdi_by_month[day.strftime("%Y-%m")]
        factor *= 1.0 + daily_pct / 100.0 * mult
    return factor


def ipca_factor(cal: Calendar, ipca_by_month: dict, start: date, end: date, real: float) -> float:
    factor = 1.0
    window = cal.business_days(start, end)
    for month_key, pct in ipca_by_month.items():
        year, month = (int(p) for p in month_key.split("-"))
        first = date(year, month, 1)
        last = date(year, month, monthrange(year, month)[1])
        du_month = len(cal.business_days(first - timedelta(days=1), last))
        du_window = sum(1 for d in window if first <= d <= last)
        if du_window:
            factor *= (1.0 + pct / 100.0) ** (du_window / du_month)
    return factor * (1.0 + real) ** (len(window) / 252.0)


def value_variable_income(asset: dict, usd_brl: float) -> dict[str, float]:
    is_usd = asset["asset_type"] in {"STOCK_INTL", "ETF_INTL", "REIT", "CRYPTO"}
    qty = cost_brl = realized_brl = 0.0
    for tx in sorted(asset["transactions"], key=lambda t: (t["date"], t["kind"] != "BUY")):
        q, price, fees, fx = (float(tx[k]) for k in ("qty", "price", "fees", "fx"))
        if tx["kind"] == "BUY":
            cost_brl += (q * price + fees) * fx
            qty += q
        else:
            avg_cost_brl = cost_brl / qty
            realized_brl += q * price * fx - q * avg_cost_brl - fees * fx
            cost_brl -= q * avg_cost_brl
            qty -= q
    invested = _cents(cost_brl)
    current = _cents(qty * asset["quote"] * (usd_brl if is_usd else 1.0))
    return {
        "invested_value_brl": invested,
        "current_value_brl": current,
        "realized_pnl_brl": _cents(realized_brl),
    }


def value_fixed_income(asset: dict, cal: Calendar, data: dict, as_of: date) -> dict[str, float]:
    term = asset["fixed_income_term"]
    (tx,) = asset["transactions"]
    start = _d(tx["date"])
    principal = float(tx["qty"]) * float(tx["price"]) + float(tx["fees"])
    rate = float(term["contracted_rate"])
    if term["indexer"] in ("CDI", "SELIC"):
        factor = cdi_factor(cal, data["cdi_daily_pct_by_month"], start, as_of, rate)
    else:
        factor = ipca_factor(cal, data["ipca_monthly_pct"], start, as_of, rate)

    gross = principal * factor
    yield_brl = gross - principal
    days = (as_of - start).days
    iof = 0.0 if term["tax_exempt"] else yield_brl * iof_rate(days)
    ir = 0.0 if term["tax_exempt"] else (yield_brl - iof) * ir_rate(days)
    return {
        "invested_value_brl": _cents(principal),
        "gross_value_brl": _cents(gross),
        "estimated_tax_brl": _cents(iof + ir),
        "current_value_brl": _cents(gross - iof - ir),
        "realized_pnl_brl": 0.0,
    }


def build_rows(data: dict) -> list[dict[str, object]]:
    cal = Calendar(data["holidays"])
    as_of = _d(data["as_of_date"])
    rows: list[dict[str, object]] = []
    totals = dict.fromkeys(
        (
            "total_invested_brl",
            "total_current_value_brl",
            "total_realized_pnl_brl",
            "total_received_earnings_brl",
            "total_consolidated_pnl_brl",
        ),
        0.0,
    )

    for asset in data["assets"]:
        if "fixed_income_term" in asset:
            values = value_fixed_income(asset, cal, data, as_of)
        else:
            values = value_variable_income(asset, data["usd_brl_rate"])
        earnings = _cents(sum(float(e["gross"]) - float(e["tax"]) for e in asset["earnings"]))
        values["received_earnings_brl"] = earnings
        values["unrealized_pnl_brl"] = _cents(
            values["current_value_brl"] - values["invested_value_brl"]
        )
        values["consolidated_pnl_brl"] = _cents(
            values["unrealized_pnl_brl"] + values["realized_pnl_brl"] + earnings
        )

        totals["total_invested_brl"] += values["invested_value_brl"]
        totals["total_current_value_brl"] += values["current_value_brl"]
        totals["total_realized_pnl_brl"] += values["realized_pnl_brl"]
        totals["total_received_earnings_brl"] += earnings
        totals["total_consolidated_pnl_brl"] += values["consolidated_pnl_brl"]

        for metric, value in values.items():
            rows.append(_row(asset["ticker"], metric, value))

    for metric, value in totals.items():
        rows.append(_row("PORTFOLIO", metric, _cents(value)))
    return rows


def _row(ticker: str, metric: str, value: float) -> dict[str, object]:
    return {
        "ticker": ticker,
        "metric": metric,
        "expected": f"{value:.2f}",
        "known_finding": KNOWN_FINDINGS.get((ticker, metric), ""),
    }


def main() -> None:
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    rows = build_rows(data)
    with OUTPUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["ticker", "metric", "expected", "known_finding"], lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT.name}")


if __name__ == "__main__":
    main()
