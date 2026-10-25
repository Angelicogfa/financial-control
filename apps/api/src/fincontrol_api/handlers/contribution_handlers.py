"""Contribution plans as an operation: suggest, keep as draft, confirm into trades (12.1)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from fincontrol_core.domain.entities import TransactionEntity
from fincontrol_core.domain.enums import ContributionPlanStatus, TransactionKind
from fincontrol_core.errors import NotFoundError
from fincontrol_core.portfolio.contribution_plans import (
    Execution,
    SavedContributionPlan,
    check_executions,
    confirm_plan,
    default_executions,
    discard_plan,
)
from fincontrol_core.portfolio.ledger import require_fx_rate, validate_ledger
from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork

from fincontrol_api.handlers.account_handlers import resolve_account_id
from fincontrol_api.handlers.serializers import to_contribution_plan_dto
from fincontrol_api.schemas import (
    ContributionConfirmRequest,
    ContributionSimulationRequest,
    SavedContributionPlanDTO,
)
from fincontrol_api.services.portfolio_service import PortfolioApplicationService

UoWFactory = Callable[[], AbstractUnitOfWork]


def to_saved_plan_dto(saved: SavedContributionPlan) -> SavedContributionPlanDTO:
    return SavedContributionPlanDTO(
        id=saved.id or 0,
        status=saved.status,
        created_at=saved.created_at,
        confirmed_at=saved.confirmed_at,
        discarded_at=saved.discarded_at,
        strategy_override=saved.strategy_override,
        policy_version=saved.policy_version,
        account_id=saved.account_id,
        transaction_ids=list(saved.transaction_ids),
        plan=to_contribution_plan_dto(saved.plan),
    )


class ContributionHandler:
    """Application handler for persisted contribution plans."""

    def __init__(
        self, uow_factory: UoWFactory, portfolio_service: PortfolioApplicationService
    ) -> None:
        self.uow_factory = uow_factory
        self.portfolio_service = portfolio_service

    def create_draft(self, req: ContributionSimulationRequest) -> SavedContributionPlanDTO:
        with self.uow_factory() as uow:
            plan = self.portfolio_service.simulate_contribution(
                uow, amount_brl=req.amount_brl, strategy_override=req.strategy_override
            )
            saved = uow.contribution_plans.add(
                SavedContributionPlan(
                    plan=plan,
                    strategy_override=req.strategy_override,
                    policy_version=self.portfolio_service.load_policy(uow).version,
                )
            )
            uow.commit()
            return to_saved_plan_dto(saved)

    def list_recent(
        self, *, status: ContributionPlanStatus | None = None, limit: int = 20
    ) -> list[SavedContributionPlanDTO]:
        with self.uow_factory() as uow:
            return [
                to_saved_plan_dto(p)
                for p in uow.contribution_plans.list_recent(status=status, limit=limit)
            ]

    def get(self, plan_id: int) -> SavedContributionPlanDTO:
        with self.uow_factory() as uow:
            return to_saved_plan_dto(self._get(uow, plan_id))

    def confirm(self, plan_id: int, req: ContributionConfirmRequest) -> SavedContributionPlanDTO:
        """Create one BUY per execution (the suggestion itself when none is given)."""
        with self.uow_factory() as uow:
            saved = self._get(uow, plan_id)
            account_id = resolve_account_id(uow, req.account_id)
            assets = {o.asset_id: uow.assets.get_by_id(o.asset_id) for o in saved.plan.orders}
            if req.executions:
                executions = [
                    Execution(
                        asset_id=e.asset_id,
                        quantity=e.quantity,
                        unit_price=e.unit_price,
                        fees=e.fees,
                        fx_rate=e.fx_rate,
                    )
                    for e in req.executions
                ]
            else:
                usd_brl = Decimal(str(self.portfolio_service.gateway.get_usd_brl_rate()))
                fx = {
                    asset_id: usd_brl
                    for asset_id, asset in assets.items()
                    if asset is not None and (asset.currency or "BRL").upper() != "BRL"
                }
                executions = default_executions(saved.plan, fx)
            check_executions(saved.plan, executions)

            transaction_ids: list[int] = []
            for execution in executions:
                asset = assets.get(execution.asset_id)
                if asset is None:
                    raise NotFoundError(f"Asset id={execution.asset_id} not found")
                require_fx_rate(asset, execution.fx_rate)
                trade = TransactionEntity(
                    asset_id=asset.id or execution.asset_id,
                    kind=TransactionKind.BUY,
                    trade_date=req.trade_date,
                    quantity=execution.quantity,
                    unit_price=execution.unit_price,
                    fees=execution.fees,
                    fx_rate=execution.fx_rate,
                    notes=f"Aporte #{saved.id}",
                    account_id=account_id,
                )
                entries = [*asset.transactions, trade]
                validate_ledger(
                    asset,
                    entries,
                    curves=self.portfolio_service.ledger_curves(uow, asset, req.trade_date),
                )
                transaction_ids.append(uow.transactions.add(trade).id or 0)

            confirmed = uow.contribution_plans.update(
                confirm_plan(
                    saved,
                    transaction_ids=transaction_ids,
                    account_id=account_id,
                    at=datetime.now(UTC),
                )
            )
            uow.commit()
            return to_saved_plan_dto(confirmed)

    def discard(self, plan_id: int) -> SavedContributionPlanDTO:
        with self.uow_factory() as uow:
            discarded = uow.contribution_plans.update(
                discard_plan(self._get(uow, plan_id), at=datetime.now(UTC))
            )
            uow.commit()
            return to_saved_plan_dto(discarded)

    @staticmethod
    def _get(uow: AbstractUnitOfWork, plan_id: int) -> SavedContributionPlan:
        saved = uow.contribution_plans.get(plan_id)
        if saved is None:
            raise NotFoundError(f"Contribution plan id={plan_id} not found")
        return saved
