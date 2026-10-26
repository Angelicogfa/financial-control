"""Unit tests for the InvestmentPolicy aggregate (item 10.1)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.errors import ValidationError
from domain.policy.services.allocation import InvalidTargetsError
from domain.policy.services.policy import (
    ArcaPolicy,
    ClassPolicy,
    EligibilityPolicy,
    InvestmentPolicy,
    ValuationPolicy,
    current_policy,
)
from domain.shared.enums import ArcaClass, IntraClassStrategy


def test_defaults_split_evenly_with_five_point_bands() -> None:
    policy = InvestmentPolicy()
    assert policy.arca.targets.weights == dict.fromkeys(ArcaClass, 25.0)
    assert set(policy.arca.bands.values()) == {5.0}
    assert set(policy.arca.strategies.values()) == {IntraClassStrategy.CERRADO}
    assert policy.eligibility.require_evaluation is False
    assert policy.valuation.bazin_required_yield == 0.06


def test_arca_policy_requires_all_classes_summing_to_100() -> None:
    with pytest.raises(InvalidTargetsError):
        ArcaPolicy({ArcaClass.ACOES: ClassPolicy(100.0)})
    with pytest.raises(InvalidTargetsError):
        ArcaPolicy(dict.fromkeys(ArcaClass, ClassPolicy(30.0)))


@pytest.mark.parametrize("band", [-1.0, 50.1])
def test_band_must_be_within_limits(band: float) -> None:
    with pytest.raises(ValidationError) as err:
        ClassPolicy(25.0, band_pct=band)
    assert err.value.code == "INVALID_BAND"


def test_eligibility_and_valuation_validation() -> None:
    with pytest.raises(ValidationError):
        EligibilityPolicy(min_coverage_pct=120.0)
    with pytest.raises(ValidationError):
        ValuationPolicy(bazin_required_yield=6.0)
    with pytest.raises(ValidationError):
        ValuationPolicy(graham_multiplier=0.0)


def test_with_arca_creates_unsaved_copy() -> None:
    saved = InvestmentPolicy(version=3)
    arca = ArcaPolicy(
        {
            ArcaClass.ACOES: ClassPolicy(40.0, band_pct=3.0),
            ArcaClass.REAL_ESTATE: ClassPolicy(20.0),
            ArcaClass.CAIXA: ClassPolicy(20.0),
            ArcaClass.ATIVOS_INTERNACIONAIS: ClassPolicy(20.0),
        }
    )
    draft = saved.with_arca(arca)
    assert draft.version is None
    assert draft.arca.bands[ArcaClass.ACOES] == 3.0
    assert draft.eligibility == saved.eligibility


def test_current_policy_falls_back_to_defaults() -> None:
    assert current_policy(SimpleNamespace(get_current=lambda: None)) == InvestmentPolicy()
