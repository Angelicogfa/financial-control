"""Alerts: what needs attention now, with dismissal (item 12.2)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta

from fincontrol_core.alerts import (
    AlertDismissal,
    data_alerts,
    portfolio_alerts,
    valuation_alerts,
    visible_alerts,
)
from fincontrol_core.domain.enums import AssetLifecycle
from fincontrol_core.market.batch import fetch_market_data
from fincontrol_core.market.series_status import TRACKED_SERIES, evaluate_series_status
from fincontrol_core.ports.unit_of_work import AbstractUnitOfWork

from fincontrol_api.schemas import AlertDismissRequest, AlertDTO, AlertsResponseDTO
from fincontrol_api.services.portfolio_service import PortfolioApplicationService

UoWFactory = Callable[[], AbstractUnitOfWork]
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
            fundamentals = fetch_market_data(
                service.gateway,
                valued,
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
