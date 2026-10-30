"""Valuation indicators from the statements known on a date and the price of that date (42.2).

The market value is the price of the traded class times all the shares (ordinary and preferred,
net of treasury): with two classes at different prices it is an approximation, as in most
screeners. Banks and insurers get only earnings yield, dividend yield and price to book.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.disclosures.statements import DIVIDENDS_PAID, NET_INCOME, SHARES, PitFundamentals


@dataclass(frozen=True)
class PitValuation:
    market_cap: float
    earnings_yield: float | None  # net income (12 months) / market value
    dividend_yield: float | None  # dividends paid (12 months) / market value
    price_to_book: float | None
    ev_to_ebitda: float | None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def valuation(fund: PitFundamentals, price: float) -> PitValuation | None:
    """Indicators at `price` (None without the share count)."""
    shares = fund.get(SHARES)
    if not shares or price <= 0:
        return None
    market_cap = price * shares
    ebitda = fund.ebitda
    net_debt = fund.net_debt
    enterprise = None if net_debt is None else market_cap + net_debt
    return PitValuation(
        market_cap=market_cap,
        earnings_yield=_ratio(fund.get(NET_INCOME), market_cap),
        dividend_yield=_ratio(fund.get(DIVIDENDS_PAID), market_cap),
        price_to_book=_ratio(market_cap, fund.controlling_equity),
        ev_to_ebitda=_ratio(enterprise, ebitda) if ebitda and ebitda > 0 else None,
    )
