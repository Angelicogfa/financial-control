"""Phase 10 acceptance: the reference portfolio under an investment policy.

Bands, exposure classes, a separate emergency reserve and lifecycle statuses must all be
consistent with the independently computed golden values (golden/*.csv).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from domain.assets.services.etf_exposure import suggest_arca_class
from domain.market.entities import Quote
from domain.policy.services.policy import InvestmentPolicy
from domain.portfolio.services.consolidation import consolidate_portfolio, plan_contribution
from domain.shared.entities import AssetEntity, TransactionEntity
from domain.shared.enums import (
    ArcaClass,
    AssetLifecycle,
    AssetPurpose,
    AssetType,
    TransactionKind,
)


def test_reference_portfolio_under_policy(
    reference_portfolio_data, reference_assets, reference_curves
) -> None:
    data = reference_portfolio_data
    policy = InvestmentPolicy()
    reserve = AssetEntity(
        id=99,
        ticker="RESERVA",
        name="Reserva de emergência",
        asset_type=AssetType.CASH,
        manual_price=Decimal("1"),
        purpose=AssetPurpose.EMERGENCY_RESERVE,
        transactions=(
            TransactionEntity(
                asset_id=99,
                kind=TransactionKind.BUY,
                trade_date=date(2025, 1, 2),
                quantity=Decimal("20000"),
                unit_price=Decimal("1"),
            ),
        ),
    )
    quotes = {r["ticker"]: Quote(r["ticker"], r["quote"]) for r in data["assets"] if "quote" in r}

    report = consolidate_portfolio(
        [*reference_assets, reserve],
        policy.arca.targets,
        quotes=quotes,
        bands=policy.arca.bands,
        eligibility=policy.eligibility,
        usd_brl_rate=data["usd_brl_rate"],
        curves=reference_curves,
        as_of_date=date.fromisoformat(data["as_of_date"]),
    )

    # Golden ARCA value (reference_portfolio_expected.csv) plus the R$ 20,000 reserve.
    assert report.value_by_purpose_brl["ARCA"] == pytest.approx(36408.43, abs=0.01)
    assert report.total_current_value_brl == pytest.approx(56408.43, abs=0.01)
    assert report.value_by_purpose_brl["EMERGENCY_RESERVE"] == 20000.0
    arca_total = sum(a.current_value for a in report.allocations)
    assert arca_total == pytest.approx(report.value_by_purpose_brl["ARCA"], abs=0.01)

    status = {a.arca_class: a.band_status for a in report.allocations}
    assert status[ArcaClass.ACOES] == "BELOW"  # 4,680 of ~36k (~13%)
    assert status[ArcaClass.REAL_ESTATE] == "BELOW"  # 1,650 (~4.5%)
    assert status[ArcaClass.CAIXA] == "ABOVE"  # CDB + LCI + Tesouro (~50%)

    lifecycles = {p.ticker: p.lifecycle_status for p in report.positions}
    assert set(lifecycles.values()) == {AssetLifecycle.HELD}

    plan = plan_contribution(report, policy.arca.targets, 5000.0)
    allocated = plan.by_class_allocated_brl
    assert allocated[ArcaClass.CAIXA] == 0.0
    assert allocated[ArcaClass.ATIVOS_INTERNACIONAIS] == 0.0
    # Classes receive what was executed (whole shares); the rest stays as cash.
    assert allocated[ArcaClass.ACOES] + allocated[ArcaClass.REAL_ESTATE] == pytest.approx(
        plan.executed_total_brl
    )
    assert plan.executed_total_brl + plan.unallocated_cash_brl == pytest.approx(5000.0)
    assert "RESERVA" not in {o.ticker for o in plan.orders}


def test_exposure_class_moves_b3_listed_global_etf() -> None:
    ivvb = AssetEntity(
        ticker="IVVB11",
        name="iShares S&P 500 (B3)",
        asset_type=AssetType.ETF_BR,
        arca_class=suggest_arca_class("IVVB11", AssetType.ETF_BR).arca_class,
    )
    assert ivvb.arca_class == ArcaClass.ATIVOS_INTERNACIONAIS
    # Without the exposure catalog the listing venue would have put it in Ações Brasil.
    assert replace(ivvb, arca_class=None).arca_class == ArcaClass.ACOES
