"""Use cases (command/query handlers) for the portfolio module.

Scope: consolidated portfolio, ARCA allocation, snapshots and analytics.
"""

from __future__ import annotations

from datetime import date

from controllers.portfolio.requests import ContributionSimulationRequest
from controllers.portfolio.responses import (
    AccountWealthDTO,
    ContributionPlanResponseDTO,
    EarningsAgendaDTO,
    MarketGroupDTO,
    PortfolioAnalyticsResponseDTO,
    PortfolioHealthDTO,
    PortfolioReportResponseDTO,
    SnapshotPointDTO,
    TreasuryMarketDTO,
    WealthByAccountDTO,
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
from domain.portfolio.services.market_split import MarketGroup, market_groups
from domain.portfolio.services.service import PortfolioApplicationService


def _group_dto(group: MarketGroup) -> MarketGroupDTO:
    return MarketGroupDTO(
        key=group.key,
        label=group.label,
        value_brl=group.value,
        invested_brl=group.invested,
        pnl_brl=group.pnl,
        change=group.change,
    )


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

    def wealth_by_account(self, *, as_of_date: date | None = None) -> WealthByAccountDTO:
        """Wealth of each account (its own trades and earnings), split into Bolsa and Internacional.

        Accounts without a position are left out; prices come from the stored quotes.
        """
        service = self.portfolio_service
        with self.uow_factory() as uow:
            whole = service.build_portfolio_report(uow, as_of_date=as_of_date)
            rows: list[AccountWealthDTO] = []
            for account in uow.accounts.list_all():
                if account.id is None:
                    continue
                report = service.build_portfolio_report(
                    uow, as_of_date=as_of_date, account_id=account.id
                )
                groups = market_groups(report.allocations)
                value = sum(g.value for g in groups)
                invested = sum(g.invested for g in groups)
                if value <= 0 and invested <= 0:
                    continue
                pnl = sum(g.pnl for g in groups)
                rows.append(
                    AccountWealthDTO(
                        account_id=account.id,
                        name=account.name,
                        institution=account.institution,
                        value_brl=round(value, 2),
                        invested_brl=round(invested, 2),
                        pnl_brl=round(pnl, 2),
                        change=pnl / invested if invested > 0 else None,
                        share=0.0,
                        groups=[_group_dto(g) for g in groups],
                    )
                )
        total = sum(r.value_brl for r in rows)
        for row in rows:
            row.share = row.value_brl / total if total > 0 else 0.0
        rows.sort(key=lambda r: r.value_brl, reverse=True)
        return WealthByAccountDTO(
            as_of_date=whole.as_of_date,
            total_value_brl=round(total, 2),
            accounts=rows,
            groups=[_group_dto(g) for g in market_groups(whole.allocations)],
        )

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
