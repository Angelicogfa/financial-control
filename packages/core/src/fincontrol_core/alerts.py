"""Actionable alerts derived from the portfolio state (item 12.2).

Each alert has a stable `key` built from what it is about (class, ticker, series, date), so a
dismissal hides it while the same condition persists and a new condition shows up again.
`route` points at the screen where the user acts on it (frontend routes, ADR 0007).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from fincontrol_core.arca.allocation import BAND_ABOVE, BAND_BELOW
from fincontrol_core.calendar import previous_business_day
from fincontrol_core.domain.entities import JobRunEntity
from fincontrol_core.domain.enums import AssetLifecycle, JobRunStatus
from fincontrol_core.fundamentals.valuation import AssetValuation, ValuationVerdict
from fincontrol_core.market.models import QuoteFreshness
from fincontrol_core.market.series_status import SeriesStatus
from fincontrol_core.portfolio.consolidation import LEDGER_INVALID, ConsolidatedPortfolioReport


class AlertSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class AlertKind(StrEnum):
    INVALID_LEDGER = "INVALID_LEDGER"
    CLASS_OUT_OF_BAND = "CLASS_OUT_OF_BAND"
    ASSET_IN_REVIEW = "ASSET_IN_REVIEW"
    PRICE_BELOW_CEILING = "PRICE_BELOW_CEILING"
    QUOTE_FALLBACK = "QUOTE_FALLBACK"
    STALE_SERIES = "STALE_SERIES"
    SNAPSHOT_MISSING = "SNAPSHOT_MISSING"
    JOB_FAILED = "JOB_FAILED"


SEVERITY_ORDER = {AlertSeverity.CRITICAL: 0, AlertSeverity.WARNING: 1, AlertSeverity.INFO: 2}


@dataclass(frozen=True)
class Alert:
    key: str
    kind: AlertKind
    severity: AlertSeverity
    title: str
    detail: str
    subject: str | None = None
    route: str | None = None


@dataclass(frozen=True)
class AlertDismissal:
    key: str
    dismissed_at: datetime
    until: date | None = None

    def active_on(self, today: date) -> bool:
        return self.until is None or today <= self.until


def _pct(value: float) -> str:
    return f"{value:.1f}%".replace(".", ",")


def portfolio_alerts(report: ConsolidatedPortfolioReport) -> list[Alert]:
    alerts: list[Alert] = []
    for position in report.positions:
        if position.ledger_status == LEDGER_INVALID:
            alerts.append(
                Alert(
                    f"ledger:{position.ticker}",
                    AlertKind.INVALID_LEDGER,
                    AlertSeverity.CRITICAL,
                    f"{position.ticker}: lançamentos inconsistentes",
                    position.ledger_message or "A posição não pode ser calculada.",
                    position.ticker,
                    f"/ledger?asset={position.asset_id}",
                )
            )
        elif position.lifecycle_status == AssetLifecycle.REVIEW:
            alerts.append(
                Alert(
                    f"review:{position.ticker}",
                    AlertKind.ASSET_IN_REVIEW,
                    AlertSeverity.WARNING,
                    f"{position.ticker} em revisão",
                    "Você tem posição, mas o ativo não atende mais à política. "
                    "Não recebe aportes até ser revisado.",
                    position.ticker,
                    f"/asset/{position.asset_id}",
                )
            )
        if (
            position.price_freshness == QuoteFreshness.FALLBACK
            and position.quantity > 0
            and position.ledger_status != LEDGER_INVALID
        ):
            alerts.append(
                Alert(
                    f"fallback:{position.ticker}",
                    AlertKind.QUOTE_FALLBACK,
                    AlertSeverity.WARNING,
                    f"{position.ticker} sem cotação",
                    "O valor usa o preço médio de compra; informe um preço manual ou aguarde "
                    "o provedor de cotações.",
                    position.ticker,
                    f"/asset/{position.asset_id}",
                )
            )
    for allocation in report.allocations:
        if allocation.band_status not in (BAND_BELOW, BAND_ABOVE):
            continue
        below = allocation.band_status == BAND_BELOW
        alerts.append(
            Alert(
                f"band:{allocation.arca_class.value}:{allocation.band_status}",
                AlertKind.CLASS_OUT_OF_BAND,
                AlertSeverity.WARNING,
                f"{allocation.label} {'abaixo' if below else 'acima'} da banda",
                f"Peso atual {_pct(allocation.current_pct)} contra meta "
                f"{_pct(allocation.target_pct)} ± {_pct(allocation.band_pct)}."
                + (" Priorize a classe no próximo aporte." if below else ""),
                allocation.arca_class.value,
                "/contribute" if below else "/portfolio",
            )
        )
    return alerts


def valuation_alerts(
    valuations: Mapping[str, AssetValuation],
    lifecycles: Mapping[str, AssetLifecycle],
    asset_ids: Mapping[str, int],
) -> list[Alert]:
    """Opportunities: eligible or held assets trading below the fair price/ceiling."""
    alerts = []
    for ticker, valuation in sorted(valuations.items()):
        status = lifecycles.get(ticker)
        if valuation.verdict != ValuationVerdict.DISCOUNTED or status not in (
            AssetLifecycle.ELIGIBLE,
            AssetLifecycle.HELD,
        ):
            continue
        margin = f" (margem {_pct((valuation.margin or 0) * 100)})" if valuation.margin else ""
        alerts.append(
            Alert(
                f"discount:{ticker}",
                AlertKind.PRICE_BELOW_CEILING,
                AlertSeverity.INFO,
                f"{ticker} abaixo do preço justo",
                f"Preço {valuation.price or 0:.2f} abaixo do valor estimado{margin}.".replace(
                    ".", ",", 1
                ),
                ticker,
                f"/asset/{asset_ids.get(ticker, 0)}",
            )
        )
    return alerts


def data_alerts(
    series: Iterable[SeriesStatus],
    *,
    latest_snapshot: date | None,
    has_positions: bool,
    job_runs: Iterable[JobRunEntity],
    today: date,
) -> list[Alert]:
    alerts = []
    for status in series:
        if not status.stale:
            continue
        last = status.last_date.isoformat() if status.last_date else "nunca"
        alerts.append(
            Alert(
                f"series:{status.symbol}:{last}",
                AlertKind.STALE_SERIES,
                AlertSeverity.WARNING,
                f"Série {status.symbol} desatualizada",
                f"Último ponto: {last}. Cálculos de renda fixa e comparativos podem estar "
                "defasados.",
                status.symbol,
                "/settings/market-data",
            )
        )
    expected = previous_business_day(today)
    if has_positions and (latest_snapshot is None or latest_snapshot < expected):
        last = latest_snapshot.isoformat() if latest_snapshot else "nenhum"
        alerts.append(
            Alert(
                f"snapshot:{expected.isoformat()}",
                AlertKind.SNAPSHOT_MISSING,
                AlertSeverity.INFO,
                "Histórico diário incompleto",
                f"Último retrato da carteira: {last}. O worker grava um por dia útil.",
                None,
                "/settings/market-data",
            )
        )
    for run in job_runs:
        if run.status != JobRunStatus.FAILED:
            continue
        alerts.append(
            Alert(
                f"job:{run.job_name}:{run.id}",
                AlertKind.JOB_FAILED,
                AlertSeverity.WARNING,
                f"Rotina {run.job_name} falhou",
                (run.error or "Sem detalhes.")[:300],
                run.job_name,
                "/settings/market-data",
            )
        )
    return alerts


def visible_alerts(
    alerts: Iterable[Alert], dismissals: Iterable[AlertDismissal], *, today: date
) -> list[Alert]:
    """Drop dismissed alerts and order by severity, then kind and subject."""
    hidden = {d.key for d in dismissals if d.active_on(today)}
    return sorted(
        (a for a in alerts if a.key not in hidden),
        key=lambda a: (SEVERITY_ORDER[a.severity], a.kind.value, a.subject or ""),
    )
