"""Command and Query Handlers for Transactions, Earnings, Portfolio, and ARCA Settings."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

from fincontrol_core.arca.allocation import ArcaTargets
from fincontrol_core.domain.entities import (
    EarningEntity,
    TransactionEntity,
)
from fincontrol_core.domain.enums import (
    ArcaClass,
    EarningKind,
    IntraClassStrategy,
    TransactionKind,
)
from fincontrol_core.domain.pagination import PaginationParams
from fincontrol_core.errors import NotFoundError
from fincontrol_core.portfolio.positions import build_position
from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork

from fincontrol_api.handlers.serializers import (
    to_contribution_plan_dto,
    to_earning_dto,
    to_page_meta_dto,
    to_portfolio_report_dto,
    to_risk_summary_dto,
    to_transaction_dto,
)
from fincontrol_api.schemas import (
    ArcaTargetItemDTO,
    ArcaTargetsUpdateRequest,
    ContributionPlanResponseDTO,
    ContributionSimulationRequest,
    EarningCreateRequest,
    EarningResponseDTO,
    PaginatedResponse,
    PortfolioAnalyticsResponseDTO,
    PortfolioReportResponseDTO,
    TransactionCreateRequest,
    TransactionResponseDTO,
)
from fincontrol_api.services.portfolio_service import PortfolioApplicationService

UoWFactory = Callable[[], AbstractUnitOfWork]


class TransactionHandler:
    """Application handler for buy/sell Transaction commands and paginated queries."""

    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def list_paginated(
        self,
        params: PaginationParams,
        *,
        asset_id: int | None = None,
        kind: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> PaginatedResponse[TransactionResponseDTO]:
        with self.uow_factory() as uow:
            assets_map = {a.id: a.ticker for a in uow.assets.list_all(active_only=False)}
            result = uow.transactions.list_paginated(
                params,
                asset_id=asset_id,
                kind=kind,
                date_from=date_from,
                date_to=date_to,
            )
            return PaginatedResponse(
                items=[
                    to_transaction_dto(t, ticker=assets_map.get(t.asset_id))
                    for t in result.items
                ],
                meta=to_page_meta_dto(result.meta),
            )

    def create(self, req: TransactionCreateRequest) -> TransactionResponseDTO:
        with self.uow_factory() as uow:
            asset = uow.assets.get_by_id(req.asset_id)
            if asset is None:
                raise NotFoundError(f"Asset id={req.asset_id} not found")

            candidate = TransactionEntity(
                asset_id=req.asset_id,
                kind=req.kind,
                trade_date=req.trade_date,
                quantity=req.quantity,
                unit_price=req.unit_price,
                fees=req.fees,
                fx_rate=req.fx_rate,
                notes=req.notes,
            )
            # Validate short-selling constraint before persisting
            if req.kind == TransactionKind.SELL:
                build_position([*asset.transactions, candidate])

            saved = uow.transactions.add(candidate)
            uow.commit()
            return to_transaction_dto(saved, ticker=asset.ticker)

    def delete(self, tx_id: int) -> None:
        with self.uow_factory() as uow:
            deleted = uow.transactions.delete(tx_id)
            if not deleted:
                raise NotFoundError(f"Transaction id={tx_id} not found")
            uow.commit()


class EarningHandler:
    """Application handler for Earnings (Proventos) commands and paginated queries."""

    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def list_paginated(
        self,
        params: PaginationParams,
        *,
        asset_id: int | None = None,
        kind: EarningKind | str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> PaginatedResponse[EarningResponseDTO]:
        with self.uow_factory() as uow:
            assets_map = {a.id: a.ticker for a in uow.assets.list_all(active_only=False)}
            kind_str = kind.value if isinstance(kind, EarningKind) else kind
            result = uow.earnings.list_paginated(
                params,
                asset_id=asset_id,
                kind=kind_str,
                date_from=date_from,
                date_to=date_to,
            )
            return PaginatedResponse(
                items=[
                    to_earning_dto(e, ticker=assets_map.get(e.asset_id)) for e in result.items
                ],
                meta=to_page_meta_dto(result.meta),
            )

    def create(self, req: EarningCreateRequest) -> EarningResponseDTO:
        with self.uow_factory() as uow:
            asset = uow.assets.get_by_id(req.asset_id)
            if asset is None:
                raise NotFoundError(f"Asset id={req.asset_id} not found")

            entity = EarningEntity(
                asset_id=req.asset_id,
                kind=req.kind,
                payment_date=req.payment_date,
                gross_amount=req.gross_amount,
                withholding_tax=req.withholding_tax,
                net_amount=req.net_amount,
                ex_date=req.ex_date,
                notes=req.notes,
                fx_rate=req.fx_rate,
            )
            saved = uow.earnings.add(entity)
            uow.commit()
            return to_earning_dto(saved, ticker=asset.ticker)

    def delete(self, earning_id: int) -> None:
        with self.uow_factory() as uow:
            deleted = uow.earnings.delete(earning_id)
            if not deleted:
                raise NotFoundError(f"Earning id={earning_id} not found")
            uow.commit()


class PortfolioHandler:
    """Application handler for Portfolio consolidation, Contribution simulator, and Analytics."""

    def __init__(
        self, uow_factory: UoWFactory, portfolio_service: PortfolioApplicationService
    ) -> None:
        self.uow_factory = uow_factory
        self.portfolio_service = portfolio_service

    def get_portfolio_report(
        self,
        *,
        as_of_date: date | None = None,
        date_from: date | None = None,
    ) -> PortfolioReportResponseDTO:
        with self.uow_factory() as uow:
            report = self.portfolio_service.build_portfolio_report(
                uow, as_of_date=as_of_date, date_from=date_from
            )
            return to_portfolio_report_dto(report)

    def simulate_contribution(
        self, req: ContributionSimulationRequest
    ) -> ContributionPlanResponseDTO:
        with self.uow_factory() as uow:
            plan = self.portfolio_service.simulate_contribution(
                uow,
                amount_brl=req.amount_brl,
                strategy_override=req.strategy_override,
            )
            return to_contribution_plan_dto(plan)

    def get_analytics(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> PortfolioAnalyticsResponseDTO:
        with self.uow_factory() as uow:
            raw = self.portfolio_service.build_portfolio_analytics(
                uow, date_from=date_from, date_to=date_to
            )
            return PortfolioAnalyticsResponseDTO(
                summary=to_risk_summary_dto(raw["summary"]),
                correlation_matrix=raw["correlation_matrix"],
                curves=raw["curves"],
            )

    def get_arca_targets(self) -> list[ArcaTargetItemDTO]:
        with self.uow_factory() as uow:
            rows = uow.arca_targets.get_all()
            if not rows:
                return [
                    ArcaTargetItemDTO(
                        arca_class=c,
                        target_pct=25.0,
                        intra_class_strategy=IntraClassStrategy.CERRADO,
                    )
                    for c in ArcaClass
                ]
            return [
                ArcaTargetItemDTO(
                    arca_class=r.arca_class,
                    target_pct=float(r.target_pct),
                    intra_class_strategy=r.intra_class_strategy,
                )
                for r in rows
            ]

    def update_arca_targets(
        self, req: ArcaTargetsUpdateRequest
    ) -> list[ArcaTargetItemDTO]:
        weights_float = {item.arca_class: item.target_pct for item in req.targets}
        # Validate sum == 100% and all 4 ARCA classes present via domain object
        ArcaTargets(weights_float)

        weights_dec = {
            item.arca_class: Decimal(str(round(item.target_pct, 4))) for item in req.targets
        }
        strategies = {item.arca_class: item.intra_class_strategy for item in req.targets}

        with self.uow_factory() as uow:
            saved = uow.arca_targets.upsert_targets(weights_dec, strategies)
            uow.commit()
            return [
                ArcaTargetItemDTO(
                    arca_class=r.arca_class,
                    target_pct=float(r.target_pct),
                    intra_class_strategy=r.intra_class_strategy,
                )
                for r in saved
            ]
