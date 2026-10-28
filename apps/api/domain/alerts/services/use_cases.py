"""Use cases (command/query handlers) for the alerts module.

Scope: portfolio, valuation and data alerts.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta

from controllers.alerts.requests import AlertDismissRequest
from controllers.alerts.responses import AlertDTO, AlertsResponseDTO
from controllers.shared.dependencies import UoWFactory
from domain.alerts.services.evaluator import (
    Alert,
    AlertDismissal,
    MaturityItem,
    agenda_alerts,
    checklist_alerts,
    data_alerts,
    data_quality_alerts,
    early_sale_alerts,
    maturity_alerts,
    portfolio_alerts,
    tax_bracket_alerts,
    valuation_alerts,
    visible_alerts,
)
from domain.market.services.series_status import TRACKED_SERIES, evaluate_series_status
from domain.portfolio.services.consolidation import ConsolidatedPortfolioReport
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.entities import AssetEntity
from domain.shared.enums import AssetLifecycle
from domain.shared.unit_of_work import AbstractUnitOfWork
from domain.tax.services.status import asset_tax_status
from infra.providers.batch import fetch_market_data

VALUED_STATUSES = frozenset({AssetLifecycle.HELD, AssetLifecycle.ELIGIBLE})


class AlertHandler:
    def __init__(
        self, uow_factory: UoWFactory, portfolio_service: PortfolioApplicationService
    ) -> None:
        self.uow_factory = uow_factory
        self.portfolio_service = portfolio_service

    def list_alerts(self, today: date | None = None) -> AlertsResponseDTO:
        reference = today or date.today()
        service = self.portfolio_service
        with self.uow_factory() as uow:
            report = service.build_portfolio_report(uow, as_of_date=reference)
            assets = {a.ticker: a for a in uow.assets.list_all(active_only=True)}
            lifecycles = {p.ticker: p.lifecycle_status for p in report.positions}
            prices = {p.ticker: p.current_unit_price for p in report.positions}
            valued = [
                assets[t] for t, s in lifecycles.items() if s in VALUED_STATUSES and t in assets
            ]
            reviewed = [
                assets[t]
                for t, s in lifecycles.items()
                if s == AssetLifecycle.REVIEW and t in assets
            ]
            fundamentals = fetch_market_data(
                service.gateway,
                [*valued, *reviewed],
                include_quotes=False,
                max_workers=service.fetch_workers,
                timeout_seconds=service.fetch_timeout_seconds,
            ).fundamentals
            valuations = {
                a.ticker: service.value(uow, a, prices.get(a.ticker), fundamentals.get(a.ticker))
                for a in valued
            }
            latest = uow.snapshots.latest_before(reference + timedelta(days=1))
            alerts = [
                *portfolio_alerts(report),
                *valuation_alerts(
                    valuations, lifecycles, {t: a.id or 0 for t, a in assets.items()}
                ),
                *data_quality_alerts(
                    fundamentals, lifecycles, {t: a.id or 0 for t, a in assets.items()}
                ),
                *checklist_alerts(report),
                *data_alerts(
                    [
                        evaluate_series_status(s, uow.market_series.list_series(s), reference)
                        for s in TRACKED_SERIES
                    ],
                    latest_snapshot=latest.snapshot_date if latest else None,
                    has_positions=any(p.quantity > 0 for p in report.positions),
                    job_runs=uow.job_runs.latest_per_job(),
                    today=reference,
                ),
            ]
            alerts.extend(self._calendar_alerts(uow, report, assets, reference))
            dismissals = uow.alert_dismissals.list_all()
        shown = visible_alerts(alerts, dismissals, today=reference)
        return AlertsResponseDTO(
            alerts=[
                AlertDTO(**{**asdict(a), "kind": a.kind.value, "severity": a.severity.value})
                for a in shown
            ],
            dismissed=len(alerts) - len(shown),
            generated_at=datetime.now(UTC),
        )

    def _calendar_alerts(
        self,
        uow: AbstractUnitOfWork,
        report: ConsolidatedPortfolioReport,
        assets: dict[str, AssetEntity],
        today: date,
    ) -> list[Alert]:
        """Phase 26 alerts: data com, maturities, tax brackets and early-sale opportunities."""
        service = self.portfolio_service
        open_positions = {
            p.ticker: p for p in report.positions if p.quantity > 0 and p.current_value_brl > 0
        }
        fixed_income = [
            a
            for t, a in assets.items()
            if t in open_positions and a.fixed_income_term is not None and a.id is not None
        ]
        maturities = [
            MaturityItem(
                a.ticker,
                a.id or 0,
                a.fixed_income_term.maturity_date,
                open_positions[a.ticker].current_value_brl,
            )
            for a in fixed_income
            if a.fixed_income_term and a.fixed_income_term.maturity_date
        ]
        rules = service.tax_rules(uow)
        statuses = [
            asset_tax_status(
                asset, today, curves=service.ledger_curves(uow, asset, today), rules=rules
            )
            for asset in fixed_income
        ]
        window = service.load_policy(uow).health.bracket_window_days
        return [
            *agenda_alerts(service.earnings_agenda(uow, as_of_date=today), today=today),
            *maturity_alerts(maturities, today=today),
            *tax_bracket_alerts(statuses, window_days=window, today=today),
            *early_sale_alerts(service.treasury_market(uow, as_of_date=today)),
        ]

    def dismiss(self, req: AlertDismissRequest) -> None:
        until = date.today() + timedelta(days=req.days) if req.days else None
        with self.uow_factory() as uow:
            uow.alert_dismissals.upsert(
                AlertDismissal(key=req.key, dismissed_at=datetime.now(UTC), until=until)
            )
            uow.commit()

    def restore(self, key: str) -> bool:
        with self.uow_factory() as uow:
            removed = uow.alert_dismissals.delete(key)
            uow.commit()
            return removed
