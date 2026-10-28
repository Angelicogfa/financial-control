"""Mark-to-market of Tesouro Direto positions and early-sale opportunities (Phase 26.1).

Two values of the same lot:
- curve: the lot accrues its own purchase rate every business day (what holding to maturity
  delivers); it is the valuation of the fixed income engine;
- market: quantity x PU de venda, the price the Treasury pays today to buy the bond back. It
  discounts the remaining cash flows at today's sell rate, so it moves against the rate: rates
  below the purchase rate put the market above the curve (a premium), rates above it put the
  market below the curve.

A premium alone does not make a sale worth it: selling and buying the same bond back only
earns today's lower rate from then on. For each open lot the engine therefore measures
1. the realized annual return of selling today versus the return the curve has delivered so
   far (`excess_rate`, both gross and nominal, so IPCA+ and prefixed lots compare alike);
2. the gross annual rate a taxable reinvestment would need until the original maturity to
   match holding the lot (`breakeven_rate`), net of income tax on both sides.
The lot is an opportunity when the excess reaches `min_excess_rate` with a premium, or when the
reference rate (projected CDI) beats the break-even by `min_reinvest_spread`.

Approximations: bonds with semiannual coupons project their maturity value without the
coupons (the comparison is flagged as approximate); IOF is ignored on the hold side.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from domain.portfolio.services.fixed_income import (
    FixedIncomeLot,
    RateCurves,
    accrual_factor,
    count_business_days,
    projection_factor,
    redemption_taxes,
    replay_lots,
    valuation_end,
)
from domain.shared.entities import AssetEntity, TransactionEntity
from domain.shared.enums import TransactionKind
from domain.tax.entities import TaxRuleBook
from domain.tax.services.rules import DEFAULT_RULE_BOOK, income_tax_regime

BUSINESS_DAYS_PER_YEAR = 252
MAX_HISTORY_POINTS = 120
STALE_PRICE_DAYS = 7


class MarketStatus(StrEnum):
    NO_MARKET_DATA = "NO_MARKET_DATA"
    BELOW_CURVE = "BELOW_CURVE"
    NEUTRAL = "NEUTRAL"
    OPPORTUNITY = "OPPORTUNITY"


class SaleSignal(StrEnum):
    EXCESS_RETURN = "EXCESS_RETURN"
    REINVESTMENT = "REINVESTMENT"


@dataclass(frozen=True)
class EarlySaleRules:
    """Thresholds of the early-sale opportunity (annual fractions, ADR 0006)."""

    min_excess_rate: float = 0.01
    min_reinvest_spread: float = 0.005


@dataclass(frozen=True)
class MarketQuoteTD:
    """Redemption price (PU de venda) and rate of a bond on `price_date`."""

    price: float
    price_date: date
    rate: float | None = None


@dataclass(frozen=True)
class QuantityLot:
    start: date
    quantity: float


@dataclass(frozen=True)
class LotMarketValue:
    start_date: date
    quantity: float
    principal: float
    purchase_rate: float | None
    curve_value: float
    market_value: float
    premium: float
    holding_days: int
    curve_annual_rate: float | None
    market_annual_rate: float | None
    excess_rate: float | None
    iof_on_sale: float
    income_tax_on_sale: float
    net_sale_value: float
    net_hold_value: float | None
    breakeven_rate: float | None
    signals: list[SaleSignal] = field(default_factory=list)


@dataclass(frozen=True)
class MarketHistoryPoint:
    day: date
    curve_value: float
    market_value: float
    premium: float


@dataclass(frozen=True)
class TreasuryMarketValuation:
    asset_id: int | None
    ticker: str
    name: str
    as_of_date: date
    status: MarketStatus
    explanation: str
    maturity_date: date | None = None
    price_date: date | None = None
    market_price: float | None = None
    market_rate: float | None = None
    stale_price: bool = False
    quantity: float = 0.0
    curve_value: float = 0.0
    market_value: float | None = None
    premium: float | None = None
    premium_pct: float | None = None
    net_sale_value: float | None = None
    reference_rate: float | None = None
    approximate: bool = False
    lots: list[LotMarketValue] = field(default_factory=list)
    history: list[MarketHistoryPoint] = field(default_factory=list)


def quantity_lots(transactions: Sequence[TransactionEntity], as_of: date) -> list[QuantityLot]:
    """Open lots by quantity on `as_of`, sales consuming the oldest purchases first."""
    ordered = sorted(
        (t for t in transactions if t.trade_date <= as_of),
        key=lambda t: (t.trade_date, t.kind != TransactionKind.BUY, t.id or 0),
    )
    lots: list[list] = []
    for tx in ordered:
        qty = float(tx.quantity)
        if tx.kind == TransactionKind.BUY:
            lots.append([tx.trade_date, qty])
            continue
        remaining = qty
        for lot in lots:
            if remaining <= 1e-12:
                break
            take = min(lot[1], remaining)
            lot[1] -= take
            remaining -= take
        lots = [lot for lot in lots if lot[1] > 1e-9]
    return [QuantityLot(start, qty) for start, qty in lots]


def _annualized(value: float, principal: float, business_days: int) -> float | None:
    if principal <= 0 or value <= 0 or business_days <= 0:
        return None
    return (value / principal) ** (BUSINESS_DAYS_PER_YEAR / business_days) - 1.0


def _pair_quantities(
    lots: Sequence[FixedIncomeLot], quantities: Sequence[QuantityLot]
) -> list[float]:
    """Quantity of each value lot: matched by order, or split by principal when they differ."""
    if len(lots) == len(quantities) and all(
        lot.start == q.start for lot, q in zip(lots, quantities, strict=True)
    ):
        return [q.quantity for q in quantities]
    total_qty = sum(q.quantity for q in quantities)
    total_principal = sum(lot.principal for lot in lots)
    if total_principal <= 0:
        return [0.0 for _ in lots]
    return [total_qty * lot.principal / total_principal for lot in lots]


def _lot_value(
    asset: AssetEntity,
    lot: FixedIncomeLot,
    quantity: float,
    end: date,
    *,
    quote: MarketQuoteTD,
    curves: RateCurves,
    rules: TaxRuleBook,
    reference_rate: float | None,
    early_sale: EarlySaleRules,
) -> LotMarketValue:
    term = asset.fixed_income_term
    assert term is not None
    curve = lot.principal * accrual_factor(term, lot.start, end, curves, rate=lot.rate).factor
    market = quantity * quote.price
    days = max(0, (end - lot.start).days)
    held_du = count_business_days(lot.start, end)
    iof, ir = redemption_taxes(
        market - lot.principal, days, tax_exempt=term.tax_exempt, on=end, rules=rules
    )
    net_sale = market - iof - ir
    curve_rate = _annualized(curve, lot.principal, held_du)
    market_rate = _annualized(market, lot.principal, held_du)
    excess = (
        market_rate - curve_rate if curve_rate is not None and market_rate is not None else None
    )

    hold_net: float | None = None
    breakeven: float | None = None
    maturity = term.maturity_date
    if maturity is not None and maturity > end and net_sale > 0:
        remaining_du = count_business_days(end, maturity)
        maturity_gross = curve * projection_factor(term, remaining_du, curves, rate=lot.rate)
        regime = income_tax_regime(tax_exempt=term.tax_exempt)
        hold_ir = rules.rule(regime, maturity).rate_for((maturity - lot.start).days)
        hold_net = maturity_gross - max(0.0, maturity_gross - lot.principal) * hold_ir
        new_ir = rules.rule(income_tax_regime(tax_exempt=False), maturity).rate_for(
            (maturity - end).days
        )
        growth = 1.0 + (hold_net / net_sale - 1.0) / (1.0 - new_ir)
        if remaining_du > 0 and growth > 0:
            breakeven = growth ** (BUSINESS_DAYS_PER_YEAR / remaining_du) - 1.0

    premium = market - curve
    signals: list[SaleSignal] = []
    if excess is not None and premium > 0 and excess >= early_sale.min_excess_rate:
        signals.append(SaleSignal.EXCESS_RETURN)
    if (
        breakeven is not None
        and reference_rate is not None
        and reference_rate - breakeven >= early_sale.min_reinvest_spread
    ):
        signals.append(SaleSignal.REINVESTMENT)
    return LotMarketValue(
        start_date=lot.start,
        quantity=round(quantity, 6),
        principal=round(lot.principal, 2),
        purchase_rate=lot.rate,
        curve_value=round(curve, 2),
        market_value=round(market, 2),
        premium=round(premium, 2),
        holding_days=days,
        curve_annual_rate=_round(curve_rate),
        market_annual_rate=_round(market_rate),
        excess_rate=_round(excess),
        iof_on_sale=round(iof, 2),
        income_tax_on_sale=round(ir, 2),
        net_sale_value=round(net_sale, 2),
        net_hold_value=round(hold_net, 2) if hold_net is not None else None,
        breakeven_rate=_round(breakeven),
        signals=signals,
    )


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def market_history(
    asset: AssetEntity,
    prices: Sequence[tuple[date, float]],
    *,
    curves: RateCurves,
    rules: TaxRuleBook,
    as_of: date,
) -> list[MarketHistoryPoint]:
    """Curve and market value of the whole position on (at most 120) past price dates."""
    term = asset.fixed_income_term
    if term is None or not asset.transactions:
        return []
    first = min(t.trade_date for t in asset.transactions)
    usable = sorted((d, p) for d, p in prices if first <= d <= as_of and p > 0)
    if not usable:
        return []
    step = max(1, math.ceil(len(usable) / MAX_HISTORY_POINTS))
    sampled = usable[::step]
    if sampled[-1] != usable[-1]:
        sampled.append(usable[-1])
    points: list[MarketHistoryPoint] = []
    for day, price in sampled:
        lots, _ = replay_lots(asset.transactions, term, day, curves=curves, tax_rules=rules)
        end = valuation_end(term, day)
        curve = sum(
            lot.principal * accrual_factor(term, lot.start, end, curves, rate=lot.rate).factor
            for lot in lots
        )
        quantity = sum(q.quantity for q in quantity_lots(asset.transactions, day))
        if quantity <= 0:
            continue
        market = quantity * price
        points.append(
            MarketHistoryPoint(
                day=day,
                curve_value=round(curve, 2),
                market_value=round(market, 2),
                premium=round(market - curve, 2),
            )
        )
    return points


def _fmt_brl(value: float) -> str:
    text = f"{abs(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{'-' if value < 0 else ''}R$ {text}"


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%".replace(".", ",")


def _explain(
    status: MarketStatus,
    premium: float | None,
    lots: Sequence[LotMarketValue],
    reference_rate: float | None,
) -> str:
    if status == MarketStatus.NO_MARKET_DATA:
        return "Sem preço de resgate do Tesouro para este título; o valor segue a curva."
    assert premium is not None
    if status == MarketStatus.BELOW_CURVE:
        return (
            f"O mercado está {_fmt_brl(-premium)} abaixo da curva: a taxa de hoje é maior que a "
            "da compra. Vender agora entrega menos que segurar até o vencimento."
        )
    best = max(lots, key=lambda lot: lot.excess_rate or -1.0)
    parts = [
        f"O mercado está {_fmt_brl(premium)} acima da curva: a taxa de hoje é menor que a "
        "da compra."
    ]
    if best.excess_rate is not None:
        parts.append(
            f"Vendendo hoje, o lote de {best.start_date.strftime('%d/%m/%Y')} renderia "
            f"{_fmt_pct(best.market_annual_rate or 0.0)} a.a. contra "
            f"{_fmt_pct(best.curve_annual_rate or 0.0)} a.a. da curva."
        )
    if best.breakeven_rate is not None:
        parts.append(
            f"Para empatar com segurar, o dinheiro precisaria render "
            f"{_fmt_pct(best.breakeven_rate)} a.a. brutos até o vencimento"
            + (
                f" (CDI projetado: {_fmt_pct(reference_rate)} a.a.)."
                if reference_rate is not None
                else "."
            )
        )
    if status == MarketStatus.NEUTRAL:
        parts.append("O ganho ainda não passa dos limites da política para sugerir a venda.")
    return " ".join(parts)


def evaluate_mark_to_market(
    asset: AssetEntity,
    as_of: date,
    *,
    quote: MarketQuoteTD | None,
    curves: RateCurves | None = None,
    rules: TaxRuleBook | None = None,
    reference_rate: float | None = None,
    early_sale: EarlySaleRules | None = None,
    price_history: Sequence[tuple[date, float]] = (),
) -> TreasuryMarketValuation:
    """Curve versus market value of a Treasury position, lot by lot, with the sale signals."""
    term = asset.fixed_income_term
    rates = curves or RateCurves()
    book = rules or DEFAULT_RULE_BOOK
    thresholds = early_sale or EarlySaleRules()
    base = {
        "asset_id": asset.id,
        "ticker": asset.ticker,
        "name": asset.name,
        "as_of_date": as_of,
        "maturity_date": term.maturity_date if term else None,
        "reference_rate": reference_rate,
        "approximate": bool(term and term.semiannual_coupons),
    }
    if term is None:
        return TreasuryMarketValuation(
            status=MarketStatus.NO_MARKET_DATA,
            explanation="O ativo não tem termos de renda fixa.",
            **base,
        )
    end = valuation_end(term, as_of)
    lots, _ = replay_lots(asset.transactions, term, as_of, curves=rates, tax_rules=book)
    quantities = _pair_quantities(lots, quantity_lots(asset.transactions, as_of))
    curve_total = sum(
        lot.principal * accrual_factor(term, lot.start, end, rates, rate=lot.rate).factor
        for lot in lots
    )
    quantity = sum(quantities)
    if quote is None or quote.price <= 0 or not lots:
        return TreasuryMarketValuation(
            status=MarketStatus.NO_MARKET_DATA,
            explanation=_explain(MarketStatus.NO_MARKET_DATA, None, [], reference_rate),
            quantity=round(quantity, 6),
            curve_value=round(curve_total, 2),
            **base,
        )

    lot_values = [
        _lot_value(
            asset,
            lot,
            qty,
            end,
            quote=quote,
            curves=rates,
            rules=book,
            reference_rate=reference_rate,
            early_sale=thresholds,
        )
        for lot, qty in zip(lots, quantities, strict=True)
    ]
    market_total = sum(lot.market_value for lot in lot_values)
    premium = market_total - curve_total
    if any(lot.signals for lot in lot_values):
        status = MarketStatus.OPPORTUNITY
    elif premium < 0:
        status = MarketStatus.BELOW_CURVE
    else:
        status = MarketStatus.NEUTRAL
    return TreasuryMarketValuation(
        status=status,
        explanation=_explain(status, premium, lot_values, reference_rate),
        price_date=quote.price_date,
        market_price=quote.price,
        market_rate=quote.rate,
        stale_price=(as_of - quote.price_date).days > STALE_PRICE_DAYS,
        quantity=round(quantity, 6),
        curve_value=round(curve_total, 2),
        market_value=round(market_total, 2),
        premium=round(premium, 2),
        premium_pct=round(premium / curve_total, 6) if curve_total > 0 else None,
        net_sale_value=round(sum(lot.net_sale_value for lot in lot_values), 2),
        lots=lot_values,
        history=market_history(asset, price_history, curves=rates, rules=book, as_of=as_of),
        **base,
    )
