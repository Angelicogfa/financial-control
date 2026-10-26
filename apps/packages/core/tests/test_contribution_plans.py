"""Unit tests for persisted contribution plans (item 12.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fincontrol_core.arca.allocation import ClassAllocation
from fincontrol_core.cerrado.scoring import Recommendation
from fincontrol_core.domain.enums import ArcaClass, AssetType, ContributionPlanStatus
from fincontrol_core.errors import ConflictError, ValidationError
from fincontrol_core.portfolio.consolidation import AssetContributionOrder, ContributionPlan
from fincontrol_core.portfolio.contribution_plans import (
    Execution,
    SavedContributionPlan,
    check_executions,
    confirm_plan,
    default_executions,
    discard_plan,
    plan_from_payload,
    plan_to_payload,
)


def _order(asset_id: int, ticker: str, qty: float, price: float) -> AssetContributionOrder:
    return AssetContributionOrder(
        asset_id=asset_id,
        ticker=ticker,
        name=ticker,
        asset_type=AssetType.STOCK_BR if asset_id == 1 else AssetType.STOCK_INTL,
        arca_class=ArcaClass.ACOES if asset_id == 1 else ArcaClass.ATIVOS_INTERNACIONAIS,
        cerrado_score=2,
        cerrado_recommendation=Recommendation.APTO,
        intra_class_target_weight_pct=100.0,
        allocated_amount_brl=qty * price,
        unit_price_brl=price,
        recommended_quantity=qty,
        executed_amount_brl=qty * price,
        projected_value_brl=qty * price,
    )


PLAN = ContributionPlan(
    contribution_amount_brl=1000.0,
    executed_total_brl=900.0,
    unallocated_cash_brl=100.0,
    by_class_allocated_brl={ArcaClass.ACOES: 400.0, ArcaClass.ATIVOS_INTERNACIONAIS: 500.0},
    orders=[_order(1, "ITUB4", 10, 40.0), _order(2, "AAPL", 2.5, 1000.0), _order(3, "X", 0, 5.0)],
    projected_allocations=[
        ClassAllocation(ArcaClass.ACOES, "Ações", 0, 400, 44.4, 25, 19.4, -150, 0, 5, "ABOVE")
    ],
)


def test_payload_round_trip_restores_enums() -> None:
    payload = plan_to_payload(PLAN)
    assert payload["orders"][0]["arca_class"] == "ACOES"
    assert payload["by_class_allocated_brl"] == {"ACOES": 400.0, "ATIVOS_INTERNACIONAIS": 500.0}
    assert plan_from_payload(payload) == PLAN


def test_default_executions_convert_foreign_prices() -> None:
    executions = default_executions(PLAN, {2: Decimal("5")})
    assert executions == [
        Execution(1, Decimal("10"), Decimal("40.000000")),
        Execution(2, Decimal("2.5"), Decimal("200.000000"), fx_rate=Decimal("5")),
    ]


def test_check_executions_rejects_empty_and_foreign_assets() -> None:
    with pytest.raises(ValidationError, match="Nothing"):
        check_executions(PLAN, [])
    with pytest.raises(ValidationError) as err:
        check_executions(PLAN, [Execution(9, Decimal("1"), Decimal("1"))])
    assert err.value.code == "ASSET_NOT_IN_PLAN"
    with pytest.raises(ValidationError):
        Execution(1, Decimal("0"), Decimal("1"))


def test_only_drafts_change_state() -> None:
    at = datetime(2026, 1, 5, tzinfo=UTC)
    draft = SavedContributionPlan(plan=PLAN, id=3)
    confirmed = confirm_plan(draft, transaction_ids=[7, 8], account_id=1, at=at)
    assert (confirmed.status, confirmed.transaction_ids, confirmed.confirmed_at) == (
        ContributionPlanStatus.CONFIRMED,
        (7, 8),
        at,
    )
    with pytest.raises(ConflictError):
        confirm_plan(confirmed, transaction_ids=[], account_id=None, at=at)
    with pytest.raises(ConflictError):
        discard_plan(confirmed, at=at)
    assert discard_plan(draft, at=at).status == ContributionPlanStatus.DISCARDED


def test_classes_report_what_they_receive_after_redistribution() -> None:
    from fincontrol_core.arca.allocation import ArcaTargets
    from fincontrol_core.domain.entities import AssetEntity
    from fincontrol_core.portfolio.consolidation import consolidate_portfolio, plan_contribution

    cash = AssetEntity(
        ticker="CAIXA", name="Reserva", asset_type=AssetType.CASH, manual_price=Decimal("1"), id=1
    )
    report = consolidate_portfolio([cash], ArcaTargets.default())
    plan = plan_contribution(report, ArcaTargets.default(), 1000.0)
    assert plan.by_class_allocated_brl[ArcaClass.CAIXA] == 1000.0
    assert plan.by_class_allocated_brl[ArcaClass.ATIVOS_INTERNACIONAIS] == 0.0
    assert sum(plan.by_class_allocated_brl.values()) == plan.executed_total_brl
