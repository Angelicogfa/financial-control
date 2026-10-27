"""Accounting quality scores from annual statements (item 29.4).

- Piotroski F-score (0-9): profitability, leverage/liquidity and efficiency signals comparing
  the last fiscal year with the previous one.
- Altman Z''-score (non-manufacturing version, Altman 1995):
  Z'' = 6.56 X1 + 3.26 X2 + 6.72 X3 + 1.05 X4, with X1 = working capital / total assets,
  X2 = retained earnings / total assets, X3 = EBIT / total assets and
  X4 = book equity / total liabilities. Zones: < 1.1 distress, 1.1-2.6 grey, > 2.6 safe.

Both need statement lines beyond the default `METRIC_KEYS`; when a line is missing the
score is None rather than a partial number. Neither score suits banks and insurers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from domain.assets.services.history import FundamentalPeriod, FundamentalSnapshot

PIOTROSKI_KEYS: tuple[str, ...] = (
    "net_income",
    "total_assets",
    "operating_cash_flow",
    "long_term_debt",
    "current_assets",
    "current_liabilities",
    "shares_outstanding",
    "gross_profit",
    "revenue",
)
ALTMAN_KEYS: tuple[str, ...] = (
    "current_assets",
    "current_liabilities",
    "total_assets",
    "retained_earnings",
    "ebit",
    "equity",
    "total_liabilities",
)

Z_DISTRESS = 1.1
Z_SAFE = 2.6


@dataclass(frozen=True)
class AccountingScores:
    f_score: int | None
    z_score: float | None

    @property
    def z_zone(self) -> str | None:
        if self.z_score is None:
            return None
        if self.z_score < Z_DISTRESS:
            return "DISTRESS"
        if self.z_score > Z_SAFE:
            return "SAFE"
        return "GREY"


def _annual(snapshots: Sequence[FundamentalSnapshot]) -> list[FundamentalSnapshot]:
    return sorted(
        (s for s in snapshots if s.period == FundamentalPeriod.ANNUAL),
        key=lambda s: s.reference_date,
    )


def _has(snapshot: FundamentalSnapshot, keys: Sequence[str]) -> bool:
    return all(snapshot.value(k) is not None for k in keys)


def _ratio(num: float, den: float) -> float:
    return num / den if den else 0.0


def piotroski_f_score(snapshots: Sequence[FundamentalSnapshot]) -> int | None:
    """F-score of the last fiscal year against the previous one (None without the lines)."""
    annual = _annual(snapshots)
    if len(annual) < 2:
        return None
    prev, last = annual[-2], annual[-1]
    if not (_has(prev, PIOTROSKI_KEYS) and _has(last, PIOTROSKI_KEYS)):
        return None

    def v(s: FundamentalSnapshot, key: str) -> float:
        return float(s.value(key) or 0.0)

    roa_last = _ratio(v(last, "net_income"), v(last, "total_assets"))
    roa_prev = _ratio(v(prev, "net_income"), v(prev, "total_assets"))
    signals = [
        roa_last > 0,
        v(last, "operating_cash_flow") > 0,
        roa_last > roa_prev,
        v(last, "operating_cash_flow") > v(last, "net_income"),
        _ratio(v(last, "long_term_debt"), v(last, "total_assets"))
        < _ratio(v(prev, "long_term_debt"), v(prev, "total_assets")),
        _ratio(v(last, "current_assets"), v(last, "current_liabilities"))
        > _ratio(v(prev, "current_assets"), v(prev, "current_liabilities")),
        v(last, "shares_outstanding") <= v(prev, "shares_outstanding"),
        _ratio(v(last, "gross_profit"), v(last, "revenue"))
        > _ratio(v(prev, "gross_profit"), v(prev, "revenue")),
        _ratio(v(last, "revenue"), v(last, "total_assets"))
        > _ratio(v(prev, "revenue"), v(prev, "total_assets")),
    ]
    return sum(1 for s in signals if s)


def altman_z_double_prime(snapshots: Sequence[FundamentalSnapshot]) -> float | None:
    """Z''-score of the last fiscal year (None without the lines or with zero denominators)."""
    annual = _annual(snapshots)
    if not annual:
        return None
    last = annual[-1]
    if not _has(last, ALTMAN_KEYS):
        return None

    def v(key: str) -> float:
        return float(last.value(key) or 0.0)

    total_assets = v("total_assets")
    total_liabilities = v("total_liabilities")
    if total_assets <= 0 or total_liabilities <= 0:
        return None
    x1 = (v("current_assets") - v("current_liabilities")) / total_assets
    x2 = v("retained_earnings") / total_assets
    x3 = v("ebit") / total_assets
    x4 = v("equity") / total_liabilities
    return round(6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4, 2)


def accounting_scores(snapshots: Sequence[FundamentalSnapshot]) -> AccountingScores:
    return AccountingScores(
        f_score=piotroski_f_score(snapshots),
        z_score=altman_z_double_prime(snapshots),
    )
