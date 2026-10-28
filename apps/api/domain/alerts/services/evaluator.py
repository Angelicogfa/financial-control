"""Actionable alerts derived from the portfolio state (item 12.2).

Each alert has a stable `key` built from what it is about (class, ticker, series, date), so a
dismissal hides it while the same condition persists and a new condition shows up again.
`route` points at the screen where the user acts on it (frontend routes, ADR 0007).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from core.helpers.calendar import previous_business_day
from domain.assets.services.valuation import AssetValuation, ValuationVerdict
from domain.market.entities import QuoteFreshness
from domain.market.services.series_status import SeriesStatus
from domain.policy.services.allocation import BAND_ABOVE, BAND_BELOW
from domain.portfolio.services.consolidation import LEDGER_INVALID, ConsolidatedPortfolioReport
from domain.portfolio.services.earnings_agenda import AgendaStatus, EarningsAgenda
from domain.portfolio.services.mark_to_market import MarketStatus, TreasuryMarketValuation
from domain.shared.entities import JobRunEntity
from domain.shared.enums import AssetLifecycle, JobRunStatus
from domain.tax.services.status import AssetTaxStatus


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
    EARNING_COM_DATE = "EARNING_COM_DATE"
    FIXED_INCOME_MATURITY = "FIXED_INCOME_MATURITY"
    TAX_BRACKET_SOON = "TAX_BRACKET_SOON"
    EARLY_SALE_OPPORTUNITY = "EARLY_SALE_OPPORTUNITY"


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


COM_DATE_WINDOW_DAYS = 7
MATURITY_WINDOW_DAYS = 30


@dataclass(frozen=True)
class MaturityItem:
    """An open fixed income position and its maturity."""

    ticker: str
    asset_id: int
    maturity_date: date
    value_brl: float


def _day(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _brl(value: float) -> str:
    text = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {text}"


def agenda_alerts(agenda: EarningsAgenda, *, today: date) -> list[Alert]:
    """Data com within a week: hold (or buy) the share until the close of that day."""
    alerts: list[Alert] = []
    limit = today + timedelta(days=COM_DATE_WINDOW_DAYS)
    for item in agenda.items:
        if item.status != AgendaStatus.UPCOMING or item.com_date is None:
            continue
        if not today <= item.com_date <= limit:
            continue
        amount = (
            f" Valor estimado para a sua posição: {_brl(item.net_amount)}."
            if item.net_amount
            else f" {item.rate:.4f} por cota.".replace(".", ",", 1)
        )
        payment = f", pagamento em {_day(item.payment_date)}" if item.payment_date else ""
        alerts.append(
            Alert(
                f"com:{item.ticker}:{item.kind.value}:{item.com_date.isoformat()}",
                AlertKind.EARNING_COM_DATE,
                AlertSeverity.INFO,
                f"{item.ticker}: data com em {_day(item.com_date)}",
                f"{item.label.capitalize()} declarado{payment}. Quem tiver a ação no fechamento "
                f"de {_day(item.com_date)} recebe; a partir de "
                f"{_day(item.ex_date or item.com_date)} ela é negociada sem o direito.{amount}",
                item.ticker,
                f"/asset/{item.asset_id}" if item.asset_id else "/research",
            )
        )
    return alerts


def maturity_alerts(items: Iterable[MaturityItem], *, today: date) -> list[Alert]:
    """Fixed income maturing within a month: plan where the money goes next."""
    alerts: list[Alert] = []
    limit = today + timedelta(days=MATURITY_WINDOW_DAYS)
    for item in items:
        if not today <= item.maturity_date <= limit:
            continue
        days = (item.maturity_date - today).days
        alerts.append(
            Alert(
                f"maturity:{item.ticker}:{item.maturity_date.isoformat()}",
                AlertKind.FIXED_INCOME_MATURITY,
                AlertSeverity.INFO,
                f"{item.ticker} vence em {days} dia(s)",
                f"Vencimento em {_day(item.maturity_date)}, com cerca de {_brl(item.value_brl)}. "
                "Planeje o reinvestimento para o dinheiro não ficar parado.",
                item.ticker,
                f"/asset/{item.asset_id}",
            )
        )
    return alerts


def tax_bracket_alerts(
    statuses: Iterable[AssetTaxStatus], *, window_days: int, today: date
) -> list[Alert]:
    """Lots whose income tax rate drops soon: redeeming before the date costs more tax."""
    alerts: list[Alert] = []
    for status in statuses:
        for lot in status.lots:
            if lot.next_bracket_date is None or lot.days_to_next_bracket is None:
                continue
            if lot.days_to_next_bracket > window_days or (lot.tax_saving_by_waiting or 0) <= 0:
                continue
            alerts.append(
                Alert(
                    f"bracket:{status.ticker}:{lot.start_date.isoformat()}:"
                    f"{lot.next_bracket_date.isoformat()}",
                    AlertKind.TAX_BRACKET_SOON,
                    AlertSeverity.INFO,
                    f"{status.ticker}: IR cai em {lot.days_to_next_bracket} dia(s)",
                    f"O lote de {_day(lot.start_date)} passa de "
                    f"{_pct(lot.income_tax_rate * 100)} para "
                    f"{_pct((lot.next_income_tax_rate or 0) * 100)} em "
                    f"{_day(lot.next_bracket_date)}; esperar economiza cerca de "
                    f"{_brl(lot.tax_saving_by_waiting or 0)} se for resgatar.",
                    status.ticker,
                    f"/asset/{status.asset_id}?tab=tax" if status.asset_id else None,
                )
            )
    return alerts


def early_sale_alerts(valuations: Iterable[TreasuryMarketValuation]) -> list[Alert]:
    """Treasury bonds whose redemption price makes an early sale worth considering."""
    alerts: list[Alert] = []
    for valuation in valuations:
        if valuation.status != MarketStatus.OPPORTUNITY or valuation.price_date is None:
            continue
        alerts.append(
            Alert(
                f"early-sale:{valuation.ticker}:{valuation.price_date.isoformat()}",
                AlertKind.EARLY_SALE_OPPORTUNITY,
                AlertSeverity.INFO,
                f"{valuation.ticker}: venda antecipada pode compensar",
                valuation.explanation,
                valuation.ticker,
                f"/asset/{valuation.asset_id}?tab=market" if valuation.asset_id else None,
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
