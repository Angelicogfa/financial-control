"""Taxed vs. exempt fixed income comparator (item 22.3).

Conventions (ADR 0006):
- `rate` is a multiplier for `CDI_PERCENT` (1.10 = 110% of CDI) and an annual fraction for
  the spread of `CDI_SPREAD`/`IPCA_SPREAD` and the rate of `PRE`.
- Projections accrue over national business days (252 per year) at the scenario's annual
  CDI/IPCA, the same premise as the 12-month projection of the fixed income engine.
- IR and IOF apply to the accumulated gain at redemption (never to the annual rate), with
  the rate in force on the redemption date for the holding period in calendar days.
- Annualized rates use 252 business days: (value / principal) ** (252 / business_days) - 1.
- Bracket equivalences use the market convention on annual rates:
  `exempt = taxed × (1 − IR)` and `taxed = exempt / (1 − IR)`.
- When terms or grace periods differ, offers are also compared over a common window (the
  shortest term); an offer whose grace period is longer than that window is flagged as
  not redeemable there.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from itertools import combinations

from core.errors import ValidationError
from core.helpers.calendar import business_days_between
from domain.policy.services.assumptions import ProjectionAssumptions
from domain.portfolio.services.fixed_income import BUSINESS_DAYS_PER_YEAR, redemption_taxes
from domain.tax.entities import TaxRegime, TaxRuleBook
from domain.tax.services.rules import DEFAULT_RULE_BOOK

MAX_TERM_DAYS = 365 * 30
DEFAULT_PRINCIPAL = 10_000.0


class OfferIndexer(StrEnum):
    """How an offer's gross yield is quoted."""

    CDI_PERCENT = "CDI_PERCENT"
    CDI_SPREAD = "CDI_SPREAD"
    IPCA_SPREAD = "IPCA_SPREAD"
    PRE = "PRE"


@dataclass(frozen=True)
class FixedIncomeOffer:
    """A bond to compare: indexer, quoted rate, term and grace period in calendar days."""

    label: str
    indexer: OfferIndexer
    rate: float
    term_days: int
    tax_exempt: bool = False
    grace_days: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.term_days <= MAX_TERM_DAYS:
            raise ValidationError(
                f"term_days of '{self.label}' must be between 1 and {MAX_TERM_DAYS}",
                code="INVALID_OFFER_TERM",
            )
        if not 0 <= self.grace_days <= self.term_days:
            raise ValidationError(
                f"grace_days of '{self.label}' must be between 0 and its term",
                code="INVALID_OFFER_GRACE",
            )
        low, high = (0.01, 5.0) if self.indexer == OfferIndexer.CDI_PERCENT else (-0.5, 1.0)
        if not low <= self.rate <= high:
            meaning = (
                "a CDI multiplier (1.10 = 110%)"
                if self.indexer == OfferIndexer.CDI_PERCENT
                else "an annual fraction (0.065 = 6.5%)"
            )
            raise ValidationError(
                f"rate {self.rate} of '{self.label}' must be {meaning} (ADR 0006)",
                code="INVALID_OFFER_RATE",
            )


@dataclass(frozen=True)
class RateScenario:
    """Annual CDI and IPCA assumed over the whole projection."""

    name: str
    annual_cdi_rate: float
    annual_ipca_rate: float


@dataclass(frozen=True)
class OfferOutcome:
    """Value of an offer redeemed after `days` calendar days."""

    days: int
    redemption_date: date
    business_days: int
    redeemable: bool
    gross_value: float
    gross_yield: float
    iof: float
    income_tax_rate: float
    income_tax: float
    net_value: float
    net_yield: float
    gross_annual_rate: float
    net_annual_rate: float


@dataclass(frozen=True)
class EquivalentRate:
    """Equivalent annual rates of an offer for one income tax bracket."""

    up_to_days: int | None
    income_tax_rate: float
    exempt_equivalent_rate: float
    taxed_equivalent_rate: float


@dataclass(frozen=True)
class OfferProjection:
    """Projection of one offer under one scenario."""

    label: str
    scenario: str
    gross_annual_rate: float
    at_maturity: OfferOutcome
    at_common_window: OfferOutcome
    equivalent_rates: tuple[EquivalentRate, ...]


@dataclass(frozen=True)
class BreakEven:
    """Holding period from which `winner` stays ahead of the other offer until the window."""

    scenario: str
    first: str
    second: str
    winner: str | None
    break_even_days: int | None
    always_ahead: bool


@dataclass(frozen=True)
class FixedIncomeComparison:
    as_of_date: date
    principal: float
    common_window_days: int
    scenarios: tuple[RateScenario, ...]
    projections: tuple[OfferProjection, ...]
    break_evens: tuple[BreakEven, ...]
    best_by_scenario: dict[str, str]


def default_scenarios(
    market_cdi: float, market_ipca: float, assumptions: ProjectionAssumptions | None = None
) -> tuple[RateScenario, ...]:
    """Base scenario from the policy (or the market) plus low/high rate scenarios."""
    premises = assumptions or ProjectionAssumptions()
    cdi = premises.projected_cdi_rate if premises.projected_cdi_rate is not None else market_cdi
    ipca = premises.projected_ipca_rate if premises.projected_ipca_rate is not None else market_ipca
    shift = premises.scenario_rate_shift
    base = RateScenario("BASE", cdi, ipca)
    if shift <= 0:
        return (base,)
    return (
        RateScenario("LOW", max(0.0, cdi - shift), ipca - shift / 2),
        base,
        RateScenario("HIGH", cdi + shift, ipca + shift / 2),
    )


def _gross_factor(offer: FixedIncomeOffer, scenario: RateScenario, business_days: int) -> float:
    years = business_days / BUSINESS_DAYS_PER_YEAR
    if offer.indexer == OfferIndexer.CDI_PERCENT:
        daily = (1.0 + scenario.annual_cdi_rate) ** (1.0 / BUSINESS_DAYS_PER_YEAR) - 1.0
        return (1.0 + daily * offer.rate) ** business_days
    if offer.indexer == OfferIndexer.CDI_SPREAD:
        return ((1.0 + scenario.annual_cdi_rate) * (1.0 + offer.rate)) ** years
    if offer.indexer == OfferIndexer.IPCA_SPREAD:
        return ((1.0 + scenario.annual_ipca_rate) * (1.0 + offer.rate)) ** years
    return (1.0 + offer.rate) ** years


def _annualize(factor: float, business_days: int) -> float:
    if business_days <= 0 or factor <= 0:
        return 0.0
    return factor ** (BUSINESS_DAYS_PER_YEAR / business_days) - 1.0


class _BusinessDayCounter:
    """Business days in (start, start + n days] for every n up to the longest term."""

    def __init__(self, start: date, max_days: int) -> None:
        business = set(business_days_between(start, start + timedelta(days=max_days)))
        counts = [0]
        for offset in range(1, max_days + 1):
            counts.append(counts[-1] + (start + timedelta(days=offset) in business))
        self._counts = counts

    def __call__(self, days: int) -> int:
        return self._counts[days]


def _outcome(
    offer: FixedIncomeOffer,
    scenario: RateScenario,
    days: int,
    *,
    start: date,
    principal: float,
    business_days: _BusinessDayCounter,
    rules: TaxRuleBook,
) -> OfferOutcome:
    bd = business_days(days)
    factor = _gross_factor(offer, scenario, bd)
    gross = principal * factor
    on = start + timedelta(days=days)
    iof, ir = redemption_taxes(
        gross - principal, days, tax_exempt=offer.tax_exempt, on=on, rules=rules
    )
    regime = (
        TaxRegime.FIXED_INCOME_EXEMPT if offer.tax_exempt else TaxRegime.FIXED_INCOME_REGRESSIVE
    )
    net = gross - iof - ir
    return OfferOutcome(
        days=days,
        redemption_date=on,
        business_days=bd,
        redeemable=days >= offer.grace_days,
        gross_value=round(gross, 2),
        gross_yield=round(gross - principal, 2),
        iof=round(iof, 2),
        income_tax_rate=rules.rate(regime, days, on),
        income_tax=round(ir, 2),
        net_value=round(net, 2),
        net_yield=round(net - principal, 2),
        gross_annual_rate=round(_annualize(factor, bd), 6),
        net_annual_rate=round(_annualize(net / principal, bd), 6),
    )


def _equivalent_rates(
    gross_annual_rate: float, on: date, rules: TaxRuleBook
) -> tuple[EquivalentRate, ...]:
    rule = rules.rule(TaxRegime.FIXED_INCOME_REGRESSIVE, on)
    return tuple(
        EquivalentRate(
            up_to_days=bracket.up_to_days,
            income_tax_rate=bracket.rate,
            exempt_equivalent_rate=round(gross_annual_rate * (1.0 - bracket.rate), 6),
            taxed_equivalent_rate=round(gross_annual_rate / (1.0 - bracket.rate), 6),
        )
        for bracket in rule.brackets
    )


def _net_curve(
    offer: FixedIncomeOffer,
    scenario: RateScenario,
    window: int,
    *,
    start: date,
    business_days: _BusinessDayCounter,
    rules: TaxRuleBook,
) -> list[float]:
    """Net value of 1.0 invested, redeemed after each day 0..window (index = days)."""
    curve = [1.0]
    for days in range(1, window + 1):
        gross = _gross_factor(offer, scenario, business_days(days))
        iof, ir = redemption_taxes(
            gross - 1.0,
            days,
            tax_exempt=offer.tax_exempt,
            on=start + timedelta(days=days),
            rules=rules,
        )
        curve.append(gross - iof - ir)
    return curve


def _break_even(
    scenario: str,
    first: FixedIncomeOffer,
    second: FixedIncomeOffer,
    curves: dict[str, list[float]],
    window: int,
) -> BreakEven:
    start_day = max(1, first.grace_days, second.grace_days)
    if start_day > window:
        return BreakEven(scenario, first.label, second.label, None, None, False)
    diffs = [curves[first.label][d] - curves[second.label][d] for d in range(start_day, window + 1)]
    final = diffs[-1]
    if abs(final) < 1e-12:
        return BreakEven(scenario, first.label, second.label, None, None, False)
    winner = first.label if final > 0 else second.label
    sign = 1.0 if final > 0 else -1.0
    since = window
    for offset in range(len(diffs) - 1, -1, -1):
        if diffs[offset] * sign < 0:
            break
        since = start_day + offset
    return BreakEven(scenario, first.label, second.label, winner, since, since == start_day)


def compare_offers(
    offers: Sequence[FixedIncomeOffer],
    scenarios: Sequence[RateScenario],
    *,
    as_of_date: date,
    principal: float = DEFAULT_PRINCIPAL,
    rules: TaxRuleBook | None = None,
) -> FixedIncomeComparison:
    """Project every offer under every scenario, net of IOF/IR on the accumulated gain."""
    if len(offers) < 2:
        raise ValidationError("Compare at least two offers", code="TOO_FEW_OFFERS")
    if len({o.label for o in offers}) != len(offers):
        raise ValidationError("Offer labels must be unique", code="DUPLICATE_OFFER_LABEL")
    if not scenarios:
        raise ValidationError("At least one scenario is required", code="NO_SCENARIOS")
    if principal <= 0:
        raise ValidationError("principal must be positive", code="INVALID_PRINCIPAL")
    book = rules or DEFAULT_RULE_BOOK
    window = min(o.term_days for o in offers)
    counter = _BusinessDayCounter(as_of_date, max(o.term_days for o in offers))

    projections: list[OfferProjection] = []
    break_evens: list[BreakEven] = []
    best: dict[str, str] = {}
    for scenario in scenarios:
        net_curves: dict[str, list[float]] = {}
        window_values: dict[str, float] = {}
        for offer in offers:
            common = dict(start=as_of_date, principal=principal, business_days=counter, rules=book)
            at_maturity = _outcome(offer, scenario, offer.term_days, **common)
            at_window = _outcome(offer, scenario, window, **common)
            year_factor = _gross_factor(offer, scenario, int(BUSINESS_DAYS_PER_YEAR))
            projections.append(
                OfferProjection(
                    label=offer.label,
                    scenario=scenario.name,
                    gross_annual_rate=round(year_factor - 1.0, 6),
                    at_maturity=at_maturity,
                    at_common_window=at_window,
                    equivalent_rates=_equivalent_rates(year_factor - 1.0, as_of_date, book),
                )
            )
            if at_window.redeemable:
                window_values[offer.label] = at_window.net_value
            net_curves[offer.label] = _net_curve(
                offer, scenario, window, start=as_of_date, business_days=counter, rules=book
            )
        if window_values:
            best[scenario.name] = max(window_values, key=lambda label: window_values[label])
        break_evens.extend(
            _break_even(scenario.name, a, b, net_curves, window) for a, b in combinations(offers, 2)
        )

    return FixedIncomeComparison(
        as_of_date=as_of_date,
        principal=principal,
        common_window_days=window,
        scenarios=tuple(scenarios),
        projections=tuple(projections),
        break_evens=tuple(break_evens),
        best_by_scenario=best,
    )
