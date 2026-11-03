"""Monthly report (Phase 48.R9): one month of the portfolio on one page, ready to print or
save as PDF — wealth at the start and at the end, contributions, result and return of the
month, income received, trades, allocation, the month's tax and the goals.

The builder is pure; `MonthlyReportHandler` reads the database and the other use cases."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from core.errors import NotFoundError, ValidationError
from domain.planning.goals import GoalProgress, GoalStatus
from domain.planning.services import GoalHandler
from domain.portfolio.services.analytics import cumulative_return, dated_time_weighted_returns
from domain.portfolio.services.income import net_brl
from domain.shared.entities import AssetEntity, PortfolioSnapshotEntity
from domain.shared.enums import TransactionKind
from domain.shared.unit_of_work import UoWFactory
from domain.tax.services.monthly import AssessedMonth, MonthlyTaxHandler, parse_month


@dataclass(frozen=True)
class ReportTrade:
    trade_date: date
    ticker: str
    kind: str
    quantity: float
    value_brl: float


@dataclass(frozen=True)
class ReportEarning:
    payment_date: date
    ticker: str
    kind: str
    net_brl: float


@dataclass(frozen=True)
class ReportClass:
    arca_class: str
    value_brl: float
    current_pct: float
    target_pct: float | None


@dataclass(frozen=True)
class ReportTax:
    tax_brl: float
    darf_brl: float
    due_date: date
    paid_on: date | None
    exempt: bool
    stock_sales_brl: float


@dataclass(frozen=True)
class ReportGoal:
    name: str
    status: GoalStatus
    progress: float
    required_monthly_brl: float


@dataclass(frozen=True)
class MonthlyReport:
    month: date  # first day
    start_date: date | None  # snapshot that opens the month (the last one before it)
    end_date: date | None  # snapshot that closes it
    start_value_brl: float
    end_value_brl: float
    bought_brl: float
    sold_brl: float
    net_flow_brl: float
    income_brl: float
    result_brl: float  # change in wealth minus the net flow plus the income received
    month_return: float | None  # time-weighted, with the income
    trades: list[ReportTrade] = field(default_factory=list)
    earnings: list[ReportEarning] = field(default_factory=list)
    allocation: list[ReportClass] = field(default_factory=list)
    tax: ReportTax | None = None
    goals: list[ReportGoal] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)


def month_end(month: date) -> date:
    return month.replace(day=calendar.monthrange(month.year, month.month)[1])


def _trade_value(qty: Decimal, price: Decimal, fx: Decimal, fees: Decimal, buy: bool) -> float:
    gross = qty * price * fx
    return float(gross + fees if buy else gross - fees)


def build_report(
    month: date,
    *,
    opening: PortfolioSnapshotEntity | None,
    in_month: list[PortfolioSnapshotEntity],
    assets: list[AssetEntity],
    tax: AssessedMonth | None = None,
    goals: list[GoalProgress] | None = None,
) -> MonthlyReport:
    """`opening` is the last snapshot before the month; `in_month` the ones inside it."""
    last = month_end(month)
    trades: list[ReportTrade] = []
    earnings: list[ReportEarning] = []
    for asset in assets:
        for t in asset.transactions:
            if month <= t.trade_date <= last:
                buy = t.kind == TransactionKind.BUY
                trades.append(
                    ReportTrade(
                        trade_date=t.trade_date,
                        ticker=asset.ticker,
                        kind=t.kind.value,
                        quantity=float(t.quantity),
                        value_brl=round(
                            _trade_value(t.quantity, t.unit_price, t.fx_rate, t.fees, buy), 2
                        ),
                    )
                )
        for e in asset.earnings:
            if month <= e.payment_date <= last:
                earnings.append(
                    ReportEarning(
                        payment_date=e.payment_date,
                        ticker=asset.ticker,
                        kind=e.kind.value,
                        net_brl=round(float(net_brl(e)), 2),
                    )
                )
    trades.sort(key=lambda t: (t.trade_date, t.ticker))
    earnings.sort(key=lambda e: (e.payment_date, e.ticker))
    bought = round(sum(t.value_brl for t in trades if t.kind == TransactionKind.BUY.value), 2)
    sold = round(sum(t.value_brl for t in trades if t.kind == TransactionKind.SELL.value), 2)
    income = round(sum(e.net_brl for e in earnings), 2)

    ordered = sorted(in_month, key=lambda s: s.snapshot_date)
    closing = ordered[-1] if ordered else None
    start_value = opening.market_value if opening else 0.0
    end_value = closing.market_value if closing else start_value
    net_flow = round(sum(s.net_flow for s in ordered), 2)
    series = ([opening] if opening else []) + ordered
    _, returns = dated_time_weighted_returns(series, purchases_at_start=True)
    month_return = round(cumulative_return(returns), 6) if returns else None

    gaps: list[str] = []
    if opening is None:
        gaps.append("Não há retrato da carteira antes do mês: o patrimônio inicial é zero.")
    if closing is None:
        gaps.append("Não há retrato da carteira dentro do mês: o resultado não pode ser medido.")

    allocation = [
        ReportClass(
            arca_class=name,
            value_brl=round(float(values.get("current_value") or 0.0), 2),
            current_pct=float(values.get("current_pct") or 0.0),
            target_pct=(
                float(values["target_pct"]) if values.get("target_pct") is not None else None
            ),
        )
        for name, values in (closing.by_class if closing else {}).items()
        if isinstance(values, dict)
    ]
    allocation.sort(key=lambda c: -c.value_brl)

    report_tax = None
    if tax is not None:
        a = tax.assessment
        report_tax = ReportTax(
            tax_brl=float(a.tax_brl),
            darf_brl=float(a.darf_brl),
            due_date=a.due_date,
            paid_on=tax.paid_on,
            exempt=a.exempt,
            stock_sales_brl=float(a.stock_sales_brl),
        )

    return MonthlyReport(
        month=month,
        start_date=opening.snapshot_date if opening else None,
        end_date=closing.snapshot_date if closing else None,
        start_value_brl=round(start_value, 2),
        end_value_brl=round(end_value, 2),
        bought_brl=bought,
        sold_brl=sold,
        net_flow_brl=net_flow,
        income_brl=income,
        result_brl=round(end_value - start_value - net_flow + income, 2) if closing else 0.0,
        month_return=month_return,
        trades=trades,
        earnings=earnings,
        allocation=allocation,
        tax=report_tax,
        goals=[
            ReportGoal(g.goal.name, g.status, g.progress, g.required_monthly_brl)
            for g in goals or []
            if g.goal.is_active
        ],
        data_gaps=gaps,
    )


class MonthlyReportHandler:
    """`GET /portfolio/monthly-report?month=YYYY-MM`."""

    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def report(self, month_text: str, *, today: date | None = None) -> MonthlyReport:
        on = today or date.today()
        month = parse_month(month_text)
        if month > on.replace(day=1):
            raise ValidationError("The month has not started yet", code="INVALID_MONTH")
        last = min(month_end(month), on)
        with self.uow_factory() as uow:
            opening = uow.snapshots.latest_before(month)
            in_month = uow.snapshots.list_range(date_from=month, date_to=last)
            assets = uow.assets.list_all(active_only=False)
        tax = self._tax(month_text, last)
        goals = GoalHandler(self.uow_factory).list(today=last)
        return build_report(
            month, opening=opening, in_month=in_month, assets=assets, tax=tax, goals=goals
        )

    def _tax(self, month_text: str, through: date) -> AssessedMonth | None:
        try:
            return MonthlyTaxHandler(self.uow_factory).month(month_text, today=through)
        except NotFoundError:
            return None
