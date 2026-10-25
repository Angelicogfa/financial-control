"""Persisted contribution plans: DRAFT -> CONFIRMED (trades created) or DISCARDED (item 12.1).

A plan stores the two-level suggestion exactly as it was shown, so confirming it later never
recomputes amounts with newer prices. Confirmation records what was actually executed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from fincontrol_core.arca.allocation import ClassAllocation
from fincontrol_core.cerrado.scoring import Recommendation
from fincontrol_core.domain.enums import (
    ArcaClass,
    AssetType,
    ContributionPlanStatus,
    IntraClassStrategy,
)
from fincontrol_core.errors import ConflictError, ValidationError
from fincontrol_core.portfolio.consolidation import AssetContributionOrder, ContributionPlan


@dataclass(frozen=True)
class SavedContributionPlan:
    plan: ContributionPlan
    status: ContributionPlanStatus = ContributionPlanStatus.DRAFT
    strategy_override: IntraClassStrategy | None = None
    policy_version: int | None = None
    account_id: int | None = None
    transaction_ids: tuple[int, ...] = ()
    created_at: datetime | None = None
    confirmed_at: datetime | None = None
    discarded_at: datetime | None = None
    id: int | None = None


@dataclass(frozen=True)
class Execution:
    """What was actually bought for one asset of the plan (price in the asset currency)."""

    asset_id: int
    quantity: Decimal
    unit_price: Decimal
    fees: Decimal = Decimal("0")
    fx_rate: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValidationError("Executed quantity must be positive")
        if self.unit_price < 0 or self.fees < 0 or self.fx_rate <= 0:
            raise ValidationError("Executed price, fees and FX rate must be valid")


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(_jsonable(k)): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if hasattr(value, "value") and isinstance(value.value, str):
        return value.value
    return value


def plan_to_payload(plan: ContributionPlan) -> dict[str, Any]:
    """JSON-safe representation stored with the plan."""
    return _jsonable(asdict(plan))


def plan_from_payload(data: Mapping[str, Any]) -> ContributionPlan:
    orders = [
        AssetContributionOrder(
            **{
                **o,
                "asset_type": AssetType(o["asset_type"]),
                "arca_class": ArcaClass(o["arca_class"]),
                "cerrado_recommendation": Recommendation(o["cerrado_recommendation"]),
            }
        )
        for o in data.get("orders", [])
    ]
    allocations = [
        ClassAllocation(**{**a, "arca_class": ArcaClass(a["arca_class"])})
        for a in data.get("projected_allocations", [])
    ]
    return ContributionPlan(
        contribution_amount_brl=float(data["contribution_amount_brl"]),
        executed_total_brl=float(data["executed_total_brl"]),
        unallocated_cash_brl=float(data["unallocated_cash_brl"]),
        by_class_allocated_brl={
            ArcaClass(k): float(v) for k, v in data.get("by_class_allocated_brl", {}).items()
        },
        orders=orders,
        projected_allocations=allocations,
    )


def default_executions(
    plan: ContributionPlan, fx_by_asset: Mapping[int, Decimal] | None = None
) -> list[Execution]:
    """Executions equal to the suggestion (BRL prices converted with each asset's FX)."""
    rates = fx_by_asset or {}
    executions = []
    for order in plan.orders:
        if order.recommended_quantity <= 0 or order.unit_price_brl <= 0:
            continue
        fx = rates.get(order.asset_id, Decimal("1"))
        executions.append(
            Execution(
                asset_id=order.asset_id,
                quantity=Decimal(str(order.recommended_quantity)),
                unit_price=(Decimal(str(order.unit_price_brl)) / fx).quantize(Decimal("0.000001")),
                fx_rate=fx,
            )
        )
    return executions


def check_executions(plan: ContributionPlan, executions: list[Execution]) -> None:
    if not executions:
        raise ValidationError("Nothing to execute in this plan", code="NOTHING_TO_EXECUTE")
    planned = {o.asset_id for o in plan.orders}
    outside = sorted({e.asset_id for e in executions} - planned)
    if outside:
        raise ValidationError(
            f"Assets {outside} are not part of this plan", code="ASSET_NOT_IN_PLAN"
        )


def _require_draft(saved: SavedContributionPlan) -> None:
    if saved.status != ContributionPlanStatus.DRAFT:
        raise ConflictError(
            f"Contribution plan #{saved.id} is {saved.status.value}", code="PLAN_NOT_DRAFT"
        )


def confirm_plan(
    saved: SavedContributionPlan,
    *,
    transaction_ids: list[int],
    account_id: int | None,
    at: datetime,
) -> SavedContributionPlan:
    _require_draft(saved)
    return replace(
        saved,
        status=ContributionPlanStatus.CONFIRMED,
        transaction_ids=tuple(transaction_ids),
        account_id=account_id,
        confirmed_at=at,
    )


def discard_plan(saved: SavedContributionPlan, *, at: datetime) -> SavedContributionPlan:
    _require_draft(saved)
    return replace(saved, status=ContributionPlanStatus.DISCARDED, discarded_at=at)
