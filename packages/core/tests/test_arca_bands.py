"""Unit tests for ARCA tolerance bands and band-aware contributions (finding A-01)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fincontrol_core.arca.allocation import (
    BAND_ABOVE,
    BAND_BELOW,
    BAND_WITHIN,
    ArcaTargets,
    band_status,
    compute_allocation,
    distribute_with_bands,
)
from fincontrol_core.domain.entities import AssetEntity, TransactionEntity
from fincontrol_core.domain.enums import ArcaClass, AssetType, TransactionKind
from fincontrol_core.portfolio.consolidation import consolidate_portfolio, plan_contribution

A, R, C, INTL = (
    ArcaClass.ACOES,
    ArcaClass.REAL_ESTATE,
    ArcaClass.CAIXA,
    ArcaClass.ATIVOS_INTERNACIONAIS,
)
TARGETS = ArcaTargets.default()


@pytest.mark.parametrize(
    ("current", "expected"),
    [(25.0, BAND_WITHIN), (20.0, BAND_WITHIN), (19.9, BAND_BELOW), (30.5, BAND_ABOVE)],
)
def test_band_status(current: float, expected: str) -> None:
    assert band_status(current, 25.0, 5.0, total=1000.0) == expected


def test_empty_portfolio_is_within_band() -> None:
    assert band_status(0.0, 25.0, 5.0, total=0.0) == BAND_WITHIN


def test_compute_allocation_reports_bands() -> None:
    allocations = compute_allocation(
        {A: 400.0, R: 100.0, C: 250.0, INTL: 250.0}, TARGETS, bands=dict.fromkeys(ArcaClass, 5.0)
    )
    status = {a.arca_class: (a.band_pct, a.band_status) for a in allocations}
    assert status[A] == (5.0, BAND_ABOVE)
    assert status[R] == (5.0, BAND_BELOW)
    assert status[C] == (5.0, BAND_WITHIN)


def test_classes_below_band_are_refilled_first() -> None:
    current = {A: 300.0, R: 100.0, C: 300.0, INTL: 300.0}

    small = distribute_with_bands(current, TARGETS, {R}, 100.0)
    large = distribute_with_bands(current, TARGETS, {R}, 1000.0)

    # R needs 25% of 1100 - 100 = 175: a 100 contribution goes entirely to it.
    assert small == {A: 0.0, R: pytest.approx(100.0), C: 0.0, INTL: 0.0}
    # With 1000, R first reaches its target (25% of 2000 = 500, deficit 400); the other
    # 600 then fills A, C and INTL up to 500 each.
    assert large == {
        A: pytest.approx(200.0),
        R: pytest.approx(400.0),
        C: pytest.approx(200.0),
        INTL: pytest.approx(200.0),
    }


def test_without_breaches_falls_back_to_target_distribution() -> None:
    current = {A: 250.0, R: 250.0, C: 250.0, INTL: 250.0}
    assert distribute_with_bands(current, TARGETS, set(), 400.0) == {
        A: pytest.approx(100.0),
        R: pytest.approx(100.0),
        C: pytest.approx(100.0),
        INTL: pytest.approx(100.0),
    }


def test_contribution_plan_prioritizes_class_below_band() -> None:
    holdings = {"CA": (A, "300"), "CR": (R, "100"), "CC": (C, "300"), "CI": (INTL, "300")}
    assets = [
        AssetEntity(
            id=i,
            ticker=ticker,
            name=ticker,
            asset_type=AssetType.CASH,
            arca_class=cls,
            manual_price=Decimal("1"),
            transactions=(
                TransactionEntity(
                    asset_id=i,
                    kind=TransactionKind.BUY,
                    trade_date=date(2025, 1, 2),
                    quantity=Decimal(qty),
                    unit_price=Decimal("1"),
                ),
            ),
        )
        for i, (ticker, (cls, qty)) in enumerate(holdings.items(), start=1)
    ]
    report = consolidate_portfolio(
        assets, TARGETS, bands=dict.fromkeys(ArcaClass, 5.0), as_of_date=date(2025, 6, 30)
    )

    plan = plan_contribution(report, TARGETS, 100.0)

    assert plan.by_class_allocated_brl[R] == pytest.approx(100.0)
    real_estate = next(a for a in plan.projected_allocations if a.arca_class == R)
    assert real_estate.band_pct == 5.0
