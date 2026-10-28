"""Sanity checks of provider indicators (Phase 25.3, part of TD-06).

Free providers sometimes return an indicator on the wrong scale (a holding's margin above
100%, a yield of 300%) or two sources disagree. Each indicator has a plausible range by asset
type, and for B3 assets the brapi value is compared with Yahoo's: a relative difference above
`MAX_DIVERGENCE` flags it. Flags live in `Fundamentals.suspicious` (field -> reason, pt-BR) and
travel with the cached data to the checklist, the valuation and the alerts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from domain.market.entities import Fundamentals
from domain.shared.enums import AssetType

MAX_DIVERGENCE = 0.30

# (low, high), inclusive; fractions follow ADR 0006 (0.12 = 12%).
DEFAULT_RANGES: dict[str, tuple[float, float]] = {
    "price_to_earnings": (-500.0, 200.0),
    "price_to_book": (0.0, 50.0),
    "dividend_yield": (0.0, 0.30),
    "return_on_equity": (-5.0, 5.0),
    "profit_margin": (-3.0, 1.0),
    "debt_to_equity": (0.0, 30.0),
    "net_debt_to_ebitda": (-30.0, 30.0),
    "revenue_growth": (-1.0, 20.0),
    "earnings_growth": (-1.0, 50.0),
}
TYPE_RANGES: dict[AssetType, dict[str, tuple[float, float]]] = {
    AssetType.FII: {"price_to_book": (0.1, 5.0), "dividend_yield": (0.0, 0.30)},
}
DIVERGENCE_FIELDS: tuple[str, ...] = (
    "price_to_earnings",
    "price_to_book",
    "dividend_yield",
    "return_on_equity",
)

LABELS: dict[str, str] = {
    "price_to_earnings": "P/L",
    "price_to_book": "P/VP",
    "dividend_yield": "dividend yield",
    "return_on_equity": "ROE",
    "profit_margin": "margem líquida",
    "debt_to_equity": "dívida/patrimônio",
    "net_debt_to_ebitda": "dívida líquida/EBITDA",
    "revenue_growth": "crescimento da receita",
    "earnings_growth": "crescimento do lucro",
}
FRACTION_FIELDS = frozenset(
    {"dividend_yield", "return_on_equity", "profit_margin", "revenue_growth", "earnings_growth"}
)


def _fmt(field: str, value: float) -> str:
    if field in FRACTION_FIELDS:
        return f"{value * 100:.1f}%".replace(".", ",")
    return f"{value:.2f}".replace(".", ",")


def ranges_for(asset_type: AssetType | None) -> dict[str, tuple[float, float]]:
    return {**DEFAULT_RANGES, **TYPE_RANGES.get(asset_type, {})} if asset_type else DEFAULT_RANGES


def range_flags(fund: Fundamentals, asset_type: AssetType | None) -> dict[str, str]:
    """Indicators outside their plausible range."""
    flags: dict[str, str] = {}
    for field, (low, high) in ranges_for(asset_type).items():
        value = getattr(fund, field, None)
        if value is None or low <= value <= high:
            continue
        flags[field] = (
            f"{LABELS[field].capitalize()} de {_fmt(field, value)} fora da faixa plausível "
            f"({_fmt(field, low)} a {_fmt(field, high)})."
        )
    return flags


def divergence_flags(
    primary: Fundamentals,
    secondary: Fundamentals | None,
    *,
    primary_name: str = "brapi",
    secondary_name: str = "Yahoo",
    max_divergence: float = MAX_DIVERGENCE,
) -> dict[str, str]:
    """Indicators whose two sources differ by more than `max_divergence` (relative)."""
    if secondary is None:
        return {}
    flags: dict[str, str] = {}
    for field in DIVERGENCE_FIELDS:
        a = getattr(primary, field, None)
        b = getattr(secondary, field, None)
        if a is None or b is None:
            continue
        scale = max(abs(a), abs(b))
        if scale <= 1e-9 or abs(a - b) / scale <= max_divergence:
            continue
        flags[field] = (
            f"{LABELS[field].capitalize()} diverge entre as fontes: {primary_name} "
            f"{_fmt(field, a)} × {secondary_name} {_fmt(field, b)}."
        )
    return flags


def check_fundamentals(
    fund: Fundamentals,
    asset_type: AssetType | None,
    secondary: Fundamentals | None = None,
) -> Fundamentals:
    """`fund` with its suspicious indicators flagged (ranges first, then divergence)."""
    flags: dict[str, str] = dict(divergence_flags(fund, secondary))
    flags.update(range_flags(fund, asset_type))
    return replace(fund, suspicious=flags)


def suspicious_fields(
    fund: Fundamentals | None, fields: Mapping[str, object] | tuple[str, ...]
) -> list[str]:
    """Which of `fields` are flagged in `fund`."""
    if fund is None or not fund.suspicious:
        return []
    return [f for f in fields if f in fund.suspicious]
