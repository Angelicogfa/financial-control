"""Tax status of a position: current bracket, next drop and the value of waiting (item 24.2).

For fixed income each open FIFO lot is taxed on its own holding period: the status shows the
rate in force today, the IOF still due, the date and days until the next (lower) bracket and
the IR estimated when redeeming today versus on that date. The projection to the next
bracket uses the annual fallback rates of `RateCurves`, the same premise as the 12-month
projection of the fixed income engine. Market assets get the informative regimes of their
type (the tax is computed on the sale or payment, outside the position).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta

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
from domain.shared.entities import AssetEntity, FixedIncomeTermEntity
from domain.shared.enums import AssetType
from domain.tax.entities import TaxBracket, TaxKind, TaxRegime, TaxRuleBook
from domain.tax.services.rules import DEFAULT_RULE_BOOK, income_tax_regime, regimes_for

IOF_FREE_AFTER_DAYS = 30


@dataclass(frozen=True)
class RegimeInfo:
    """Rule of a tax regime in force on the reference date."""

    regime: TaxRegime
    tax_kind: TaxKind
    current_rate: float
    brackets: tuple[TaxBracket, ...]
    valid_from: date
    valid_to: date | None
    legal_basis: str
    description: str


@dataclass(frozen=True)
class LotTaxStatus:
    """Taxes of one open lot if redeemed today and on the date of its next bracket."""

    start_date: date
    principal: float
    gross_value: float
    gross_yield: float
    holding_days: int
    income_tax_rate: float
    iof_rate: float
    iof_due: float
    iof_free_date: date | None
    income_tax_due: float
    net_value: float
    next_bracket_date: date | None = None
    days_to_next_bracket: int | None = None
    next_income_tax_rate: float | None = None
    projected_gross_at_next_bracket: float | None = None
    tax_at_next_bracket: float | None = None
    tax_saving_by_waiting: float | None = None
    net_gain_by_waiting: float | None = None


@dataclass(frozen=True)
class AssetTaxStatus:
    """Tax status of an asset: regimes of its type and, for fixed income, each open lot."""

    asset_id: int | None
    ticker: str
    asset_type: AssetType
    as_of_date: date
    is_fixed_income: bool
    tax_exempt: bool
    regimes: tuple[RegimeInfo, ...]
    lots: tuple[LotTaxStatus, ...] = ()
    invested_principal: float = 0.0
    gross_value: float = 0.0
    iof_due: float = 0.0
    income_tax_due: float = 0.0
    net_value: float = 0.0
    next_bracket_date: date | None = None
    tax_saving_by_waiting: float = 0.0


def regime_infos(
    regimes: tuple[TaxRegime, ...], on: date, rules: TaxRuleBook
) -> tuple[RegimeInfo, ...]:
    infos = []
    for regime in regimes:
        rule = rules.rule(regime, on)
        infos.append(
            RegimeInfo(
                regime=rule.regime,
                tax_kind=rule.tax_kind,
                current_rate=rule.brackets[0].rate,
                brackets=rule.brackets,
                valid_from=rule.valid_from,
                valid_to=rule.valid_to,
                legal_basis=rule.legal_basis,
                description=rule.description,
            )
        )
    return tuple(infos)


def lot_tax_status(
    lot: FixedIncomeLot,
    term: FixedIncomeTermEntity,
    as_of_date: date,
    *,
    curves: RateCurves,
    rules: TaxRuleBook,
) -> LotTaxStatus:
    """Taxes of `lot` redeemed on `as_of_date` (capped at maturity) and at its next bracket."""
    end = valuation_end(term, as_of_date)
    gross = lot.principal * accrual_factor(term, lot.start, end, curves).factor
    days = max(0, (end - lot.start).days)
    exempt = term.tax_exempt
    iof, ir = redemption_taxes(gross - lot.principal, days, tax_exempt=exempt, on=end, rules=rules)
    rule = rules.rule(income_tax_regime(tax_exempt=exempt), end)
    ir_rate = rule.rate_for(days)
    iof_rate = iof / (gross - lot.principal) if gross > lot.principal and iof > 0 else 0.0
    net = gross - iof - ir
    base = LotTaxStatus(
        start_date=lot.start,
        principal=round(lot.principal, 2),
        gross_value=round(gross, 2),
        gross_yield=round(gross - lot.principal, 2),
        holding_days=days,
        income_tax_rate=ir_rate,
        iof_rate=round(iof_rate, 4),
        iof_due=round(iof, 2),
        iof_free_date=(lot.start + timedelta(days=IOF_FREE_AFTER_DAYS) if iof > 0 else None),
        income_tax_due=round(ir, 2),
        net_value=round(net, 2),
    )

    upcoming = rule.next_bracket(days)
    matured = term.maturity_date is not None and end >= term.maturity_date
    if upcoming is None or matured:
        return base
    next_date = lot.start + timedelta(days=upcoming.from_days)
    if term.maturity_date is not None and next_date > term.maturity_date:
        return base

    gross_next = gross * projection_factor(term, count_business_days(end, next_date), curves)
    yield_next = gross_next - lot.principal
    iof_next, ir_next = redemption_taxes(
        yield_next, upcoming.from_days, tax_exempt=exempt, on=next_date, rules=rules
    )
    tax_next = iof_next + ir_next
    taxed_at_current_rate = max(0.0, yield_next - iof_next) * ir_rate + iof_next
    next_rate = rules.rule(income_tax_regime(tax_exempt=exempt), next_date).rate_for(
        upcoming.from_days
    )
    return replace(
        base,
        next_bracket_date=next_date,
        days_to_next_bracket=(next_date - end).days,
        next_income_tax_rate=next_rate,
        projected_gross_at_next_bracket=round(gross_next, 2),
        tax_at_next_bracket=round(tax_next, 2),
        tax_saving_by_waiting=round(taxed_at_current_rate - tax_next, 2),
        net_gain_by_waiting=round(gross_next - tax_next - net, 2),
    )


def asset_tax_status(
    asset: AssetEntity,
    as_of_date: date,
    *,
    curves: RateCurves | None = None,
    rules: TaxRuleBook | None = None,
) -> AssetTaxStatus:
    """Tax status of `asset` on `as_of_date` (lots only for assets with fixed income terms)."""
    book = rules or DEFAULT_RULE_BOOK
    term = asset.fixed_income_term
    regimes = regime_infos(regimes_for(asset.asset_type, term), as_of_date, book)
    if term is None:
        return AssetTaxStatus(
            asset_id=asset.id,
            ticker=asset.ticker,
            asset_type=asset.asset_type,
            as_of_date=as_of_date,
            is_fixed_income=False,
            tax_exempt=False,
            regimes=regimes,
        )

    rates = curves or RateCurves()
    lots, _realized = replay_lots(
        asset.transactions, term, as_of_date, curves=rates, tax_rules=book
    )
    statuses = tuple(
        lot_tax_status(lot, term, as_of_date, curves=rates, rules=book) for lot in lots
    )
    upcoming = [s.next_bracket_date for s in statuses if s.next_bracket_date is not None]
    return AssetTaxStatus(
        asset_id=asset.id,
        ticker=asset.ticker,
        asset_type=asset.asset_type,
        as_of_date=as_of_date,
        is_fixed_income=True,
        tax_exempt=term.tax_exempt,
        regimes=regimes,
        lots=statuses,
        invested_principal=round(sum(s.principal for s in statuses), 2),
        gross_value=round(sum(s.gross_value for s in statuses), 2),
        iof_due=round(sum(s.iof_due for s in statuses), 2),
        income_tax_due=round(sum(s.income_tax_due for s in statuses), 2),
        net_value=round(sum(s.net_value for s in statuses), 2),
        next_bracket_date=min(upcoming) if upcoming else None,
        tax_saving_by_waiting=round(sum(s.tax_saving_by_waiting or 0.0 for s in statuses), 2),
    )
