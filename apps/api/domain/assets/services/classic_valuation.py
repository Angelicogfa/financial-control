"""Classic valuation indicators (Graham fair value, Bazin ceiling price, margin of safety)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from domain.market.entities import Fundamentals

GRAHAM_CONSTANT = 22.5
BAZIN_DEFAULT_YIELD = 0.06


def graham_fair_value(
    eps: float | None, bvps: float | None, multiplier: float = GRAHAM_CONSTANT
) -> float | None:
    """Benjamin Graham fair price: sqrt(22.5 * EPS * BVPS). Undefined when EPS or BVPS <= 0."""
    if eps is None or bvps is None or eps <= 0 or bvps <= 0:
        return None
    return math.sqrt(multiplier * eps * bvps)


def bazin_ceiling_price(
    dividends_per_share: float | None,
    required_yield: float = BAZIN_DEFAULT_YIELD,
) -> float | None:
    """Decio Bazin ceiling price: annual DPS / required dividend yield (default 6%)."""
    if dividends_per_share is None or dividends_per_share <= 0 or required_yield <= 0:
        return None
    return dividends_per_share / required_yield


def margin_of_safety(fair_value: float | None, price: float | None) -> float | None:
    """Margin of safety as a fraction: (fair_value - current_price) / fair_value."""
    if fair_value is None or price is None or fair_value <= 0:
        return None
    return (fair_value - price) / fair_value


@dataclass(frozen=True)
class ValuationSummary:
    """Valuation indicators summary for a variable income asset."""

    price: float | None
    graham_fair_value: float | None
    graham_margin: float | None
    bazin_ceiling_price: float | None
    bazin_margin: float | None
    earnings_yield: float | None


def summarize_valuation(
    price: float | None,
    f: Fundamentals | None,
    *,
    bazin_required_yield: float = BAZIN_DEFAULT_YIELD,
    graham_multiplier: float = GRAHAM_CONSTANT,
) -> ValuationSummary:
    """Compute Graham, Bazin, margins of safety, and earnings yield from fundamentals."""
    if f is None:
        return ValuationSummary(price, None, None, None, None, None)
    graham = graham_fair_value(f.earnings_per_share, f.book_value_per_share, graham_multiplier)
    dps = f.dividends_per_share_ttm
    if dps is None and f.dividend_yield is not None and price:
        dps = f.dividend_yield * price
    bazin = bazin_ceiling_price(dps, bazin_required_yield)
    ey = 1.0 / f.price_to_earnings if f.price_to_earnings and f.price_to_earnings > 0 else None
    return ValuationSummary(
        price=price,
        graham_fair_value=round(graham, 2) if graham is not None else None,
        graham_margin=round(margin_of_safety(graham, price) or 0.0, 4)
        if graham is not None and price is not None
        else None,
        bazin_ceiling_price=round(bazin, 2) if bazin is not None else None,
        bazin_margin=round(margin_of_safety(bazin, price) or 0.0, 4)
        if bazin is not None and price is not None
        else None,
        earnings_yield=round(ey, 4) if ey is not None else None,
    )
