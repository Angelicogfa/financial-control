"""Unit tests for the taxed vs. exempt fixed income comparator (item 22.3)."""

from __future__ import annotations

from datetime import date

import pytest

from core.errors import ValidationError
from core.helpers.calendar import business_days_between
from domain.policy.services.assumptions import ProjectionAssumptions
from domain.tax.services.comparator import (
    FixedIncomeOffer,
    OfferIndexer,
    RateScenario,
    compare_offers,
    default_scenarios,
)

START = date(2026, 11, 3)
BASE = RateScenario("BASE", 0.14, 0.045)


def _bd(days: int) -> int:
    from datetime import timedelta

    return len(business_days_between(START, START + timedelta(days=days)))


def _projection(result, label: str, scenario: str = "BASE"):  # type: ignore[no-untyped-def]
    return next(p for p in result.projections if p.label == label and p.scenario == scenario)


def test_ir_applies_to_the_accumulated_gain_not_to_the_annual_rate() -> None:
    cdb = FixedIncomeOffer("CDB", OfferIndexer.CDI_PERCENT, 1.10, 800)
    lca = FixedIncomeOffer("LCA", OfferIndexer.CDI_PERCENT, 0.90, 800, tax_exempt=True)
    result = compare_offers([cdb, lca], [BASE], as_of_date=START, principal=10_000)

    taxed = _projection(result, "CDB").at_maturity
    assert taxed.income_tax_rate == 0.15
    assert taxed.iof == 0.0
    assert taxed.income_tax == pytest.approx(taxed.gross_yield * 0.15, abs=0.02)
    assert taxed.net_value == pytest.approx(10_000 + taxed.gross_yield * 0.85, abs=0.02)
    # The net annual rate is not simply gross annual × (1 − IR) because the tax hits the
    # compounded gain once.
    gross_rate = _projection(result, "CDB").gross_annual_rate
    assert taxed.net_annual_rate != pytest.approx(gross_rate * 0.85, abs=1e-6)
    assert taxed.net_annual_rate > gross_rate * 0.85

    exempt = _projection(result, "LCA").at_maturity
    assert exempt.income_tax == 0.0
    assert exempt.net_value == exempt.gross_value
    assert exempt.net_annual_rate == pytest.approx(exempt.gross_annual_rate, abs=1e-6)


def test_cdi_percent_projection_formula() -> None:
    offer = FixedIncomeOffer("A", OfferIndexer.CDI_PERCENT, 1.0, 365)
    other = FixedIncomeOffer("B", OfferIndexer.PRE, 0.10, 365)
    result = compare_offers([offer, other], [BASE], as_of_date=START, principal=1000)
    bd = _bd(365)
    daily = (1.14) ** (1 / 252) - 1
    assert _projection(result, "A").at_maturity.gross_value == pytest.approx(
        1000 * (1 + daily) ** bd, abs=0.01
    )
    assert _projection(result, "A").gross_annual_rate == pytest.approx(0.14, abs=1e-6)


@pytest.mark.parametrize(
    ("indexer", "rate", "annual"),
    [
        (OfferIndexer.PRE, 0.13, 0.13),
        (OfferIndexer.IPCA_SPREAD, 0.07, 1.045 * 1.07 - 1),
        (OfferIndexer.CDI_SPREAD, 0.01, 1.14 * 1.01 - 1),
    ],
)
def test_annual_rate_by_indexer(indexer: OfferIndexer, rate: float, annual: float) -> None:
    offer = FixedIncomeOffer("X", indexer, rate, 1000)
    ref = FixedIncomeOffer("REF", OfferIndexer.CDI_PERCENT, 1.0, 1000)
    result = compare_offers([offer, ref], [BASE], as_of_date=START, principal=1000)
    projection = _projection(result, "X")
    assert projection.gross_annual_rate == pytest.approx(annual, abs=1e-6)
    bd = _bd(1000)
    assert projection.at_maturity.gross_value == pytest.approx(
        1000 * (1 + annual) ** (bd / 252), abs=0.01
    )
    assert projection.at_maturity.gross_annual_rate == pytest.approx(annual, abs=1e-5)


def test_equivalent_rates_by_bracket() -> None:
    cdb = FixedIncomeOffer("CDB", OfferIndexer.PRE, 0.12, 400)
    lci = FixedIncomeOffer("LCI", OfferIndexer.PRE, 0.10, 400, tax_exempt=True)
    result = compare_offers([cdb, lci], [BASE], as_of_date=START)
    rates = {r.up_to_days: r for r in _projection(result, "CDB").equivalent_rates}
    assert set(rates) == {180, 360, 720, None}
    assert rates[180].exempt_equivalent_rate == pytest.approx(0.12 * 0.775, abs=1e-6)
    assert rates[None].exempt_equivalent_rate == pytest.approx(0.12 * 0.85, abs=1e-6)
    lci_rates = {r.up_to_days: r for r in _projection(result, "LCI").equivalent_rates}
    assert lci_rates[720].taxed_equivalent_rate == pytest.approx(0.10 / 0.825, abs=1e-6)


def test_iof_on_redemptions_before_30_days() -> None:
    short = FixedIncomeOffer("D29", OfferIndexer.CDI_PERCENT, 1.0, 29)
    longer = FixedIncomeOffer("D30", OfferIndexer.CDI_PERCENT, 1.0, 30)
    result = compare_offers([short, longer], [BASE], as_of_date=START, principal=10_000)
    d29 = _projection(result, "D29").at_maturity
    d30 = _projection(result, "D30").at_maturity
    assert d29.iof == pytest.approx(d29.gross_yield * 0.03, abs=0.01)
    assert d29.income_tax == pytest.approx((d29.gross_yield - d29.iof) * 0.225, abs=0.01)
    assert d30.iof == 0.0


def test_common_window_and_grace_periods() -> None:
    short = FixedIncomeOffer("CURTO", OfferIndexer.CDI_PERCENT, 1.0, 365)
    long_locked = FixedIncomeOffer("LONGO", OfferIndexer.IPCA_SPREAD, 0.07, 1500, grace_days=1500)
    daily = FixedIncomeOffer("DIARIO", OfferIndexer.CDI_PERCENT, 1.05, 1000, grace_days=0)
    result = compare_offers([short, long_locked, daily], [BASE], as_of_date=START)

    assert result.common_window_days == 365
    locked = _projection(result, "LONGO")
    assert locked.at_common_window.days == 365
    assert not locked.at_common_window.redeemable
    assert locked.at_maturity.redeemable
    assert _projection(result, "DIARIO").at_common_window.redeemable
    # The locked bond cannot win inside the window.
    assert result.best_by_scenario["BASE"] == "DIARIO"
    no_overlap = next(b for b in result.break_evens if {b.first, b.second} == {"CURTO", "LONGO"})
    assert no_overlap.winner is None and no_overlap.break_even_days is None


def test_break_even_between_taxed_and_exempt() -> None:
    # 100% CDI taxed vs 85% CDI exempt: the exempt wins while IR is 22.5%/20%, and the
    # taxed overtakes once IR drops to 15% (100% × 0.85 = 85%, plus compounding).
    cdb = FixedIncomeOffer("CDB", OfferIndexer.CDI_PERCENT, 1.0, 1100)
    lca = FixedIncomeOffer("LCA", OfferIndexer.CDI_PERCENT, 0.85, 1100, tax_exempt=True)
    result = compare_offers([cdb, lca], [BASE], as_of_date=START)
    breakeven = result.break_evens[0]
    assert breakeven.winner == "CDB"
    assert breakeven.break_even_days == 721
    assert not breakeven.always_ahead


def test_dominant_offer_is_always_ahead() -> None:
    better = FixedIncomeOffer("A", OfferIndexer.PRE, 0.15, 400, tax_exempt=True)
    worse = FixedIncomeOffer("B", OfferIndexer.PRE, 0.10, 400)
    result = compare_offers([better, worse], [BASE], as_of_date=START)
    assert result.break_evens[0].winner == "A"
    assert result.break_evens[0].always_ahead
    assert result.break_evens[0].break_even_days == 1


def test_scenarios_change_the_outcome_of_floating_rates() -> None:
    pre = FixedIncomeOffer("PRE", OfferIndexer.PRE, 0.14, 720)
    cdi = FixedIncomeOffer("CDI", OfferIndexer.CDI_PERCENT, 1.0, 720)
    scenarios = default_scenarios(0.14, 0.045, ProjectionAssumptions())
    result = compare_offers([pre, cdi], scenarios, as_of_date=START)
    assert [s.name for s in result.scenarios] == ["LOW", "BASE", "HIGH"]
    assert result.best_by_scenario["LOW"] == "PRE"
    assert result.best_by_scenario["HIGH"] == "CDI"
    assert _projection(result, "PRE", "LOW").at_maturity.net_value == (
        _projection(result, "PRE", "HIGH").at_maturity.net_value
    )


def test_default_scenarios_use_policy_premises() -> None:
    premises = ProjectionAssumptions(
        projected_cdi_rate=0.12, projected_ipca_rate=0.04, scenario_rate_shift=0.03
    )
    low, base, high = default_scenarios(0.15, 0.05, premises)
    assert (base.annual_cdi_rate, base.annual_ipca_rate) == (0.12, 0.04)
    assert low.annual_cdi_rate == pytest.approx(0.09)
    assert high.annual_ipca_rate == pytest.approx(0.055)
    market = default_scenarios(0.15, 0.05, ProjectionAssumptions(scenario_rate_shift=0.0))
    assert market == (RateScenario("BASE", 0.15, 0.05),)
    assert default_scenarios(0.01, 0.05)[0].annual_cdi_rate == 0.0


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"term_days": 0}, "INVALID_OFFER_TERM"),
        ({"grace_days": 500}, "INVALID_OFFER_GRACE"),
        ({"rate": 9.0}, "INVALID_OFFER_RATE"),
        ({"indexer": OfferIndexer.PRE, "rate": 2.0}, "INVALID_OFFER_RATE"),
    ],
)
def test_invalid_offers(kwargs: dict[str, object], code: str) -> None:
    params: dict[str, object] = {
        "label": "X",
        "indexer": OfferIndexer.CDI_PERCENT,
        "rate": 1.0,
        "term_days": 365,
    }
    params.update(kwargs)
    with pytest.raises(ValidationError) as exc:
        FixedIncomeOffer(**params)  # type: ignore[arg-type]
    assert exc.value.code == code


def test_comparison_input_validation() -> None:
    a = FixedIncomeOffer("A", OfferIndexer.PRE, 0.1, 100)
    b = FixedIncomeOffer("B", OfferIndexer.PRE, 0.1, 100)
    with pytest.raises(ValidationError, match="two offers"):
        compare_offers([a], [BASE], as_of_date=START)
    with pytest.raises(ValidationError, match="unique"):
        compare_offers([a, a], [BASE], as_of_date=START)
    with pytest.raises(ValidationError, match="scenario"):
        compare_offers([a, b], [], as_of_date=START)
    with pytest.raises(ValidationError, match="principal"):
        compare_offers([a, b], [BASE], as_of_date=START, principal=0)
