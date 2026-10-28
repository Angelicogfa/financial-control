"""Use cases (command/query handlers) for the portfolio module.

Scope: consolidated portfolio, ARCA allocation, snapshots and analytics.
"""

from __future__ import annotations

from datetime import date

from controllers.portfolio.requests import ContributionSimulationRequest
from controllers.portfolio.responses import (
    ContributionPlanResponseDTO,
    EarningsAgendaDTO,
    PortfolioAnalyticsResponseDTO,
    PortfolioHealthDTO,
    PortfolioReportResponseDTO,
    SnapshotPointDTO,
    TreasuryMarketDTO,
)
from controllers.portfolio.serializers import (
    to_contribution_plan_dto,
    to_earnings_agenda_dto,
    to_portfolio_health_dto,
    to_portfolio_report_dto,
    to_risk_summary_dto,
    to_treasury_market_dto,
)
from controllers.shared.dependencies import UoWFactory
from core.errors import NotFoundError
from domain.accounts.services.use_cases import resolve_account_id
from domain.portfolio.services.service import PortfolioApplicationService


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
        account_id: int | None = None,
    ) -> PortfolioReportResponseDTO:
        with self.uow_factory() as uow:
            report = self.portfolio_service.build_portfolio_report(
                uow,
                as_of_date=as_of_date,
                date_from=date_from,
                account_id=resolve_account_id(uow, account_id),
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

    def list_snapshots(
        self, *, date_from: date | None = None, date_to: date | None = None
    ) -> list[SnapshotPointDTO]:
        with self.uow_factory() as uow:
            snapshots = uow.snapshots.list_range(date_from=date_from, date_to=date_to)
        return [
            SnapshotPointDTO(
                snapshot_date=s.snapshot_date,
                invested_value=float(s.invested_value),
                market_value=float(s.market_value),
                consolidated_pnl=float(s.consolidated_pnl),
                earnings_cum=float(s.earnings_cum),
                net_flow=float(s.net_flow),
            )
            for s in sorted(snapshots, key=lambda s: s.snapshot_date)
        ]

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
                status=raw["status"],
                available_points=raw["available_points"],
                summary=to_risk_summary_dto(raw["summary"]),
                correlation_matrix=raw["correlation_matrix"],
                curves=raw["curves"],
            )

    def get_health(self, *, as_of_date: date | None = None) -> PortfolioHealthDTO:
        with self.uow_factory() as uow:
            report = self.portfolio_service.build_portfolio_health(uow, as_of_date=as_of_date)
        return to_portfolio_health_dto(report)

    def treasury_market(
        self,
        *,
        as_of_date: date | None = None,
        asset_id: int | None = None,
        with_history: bool = False,
    ) -> list[TreasuryMarketDTO]:
        with self.uow_factory() as uow:
            valuations = self.portfolio_service.treasury_market(
                uow, as_of_date=as_of_date, asset_id=asset_id, with_history=with_history
            )
        return [to_treasury_market_dto(v) for v in valuations]

    def treasury_market_detail(
        self, asset_id: int, *, as_of_date: date | None = None
    ) -> TreasuryMarketDTO:
        found = self.treasury_market(as_of_date=as_of_date, asset_id=asset_id, with_history=True)
        if not found:
            raise NotFoundError(f"No open Treasury position for asset id={asset_id}")
        return found[0]

    def earnings_agenda(self, *, as_of_date: date | None = None) -> EarningsAgendaDTO:
        with self.uow_factory() as uow:
            agenda = self.portfolio_service.earnings_agenda(uow, as_of_date=as_of_date)
        return to_earnings_agenda_dto(agenda)
