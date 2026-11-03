"""Use cases of the monthly income tax (Phase 48.R7, Carteira › Imposto).

The assessment is recomputed from the ledger on each read and the figures are kept in
`monthly_tax_assessments` with the day each DARF was paid. Nothing here writes to the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from core.errors import NotFoundError, ValidationError
from domain.alerts.services.evaluator import Alert, AlertKind, AlertSeverity
from domain.shared.unit_of_work import AbstractUnitOfWork, UoWFactory
from domain.tax.assessment import (
    ForeignYear,
    LedgerIssue,
    MonthAssessment,
    Sale,
    assess_foreign,
    assess_months,
    realized_sales,
)
from domain.tax.repositories import StoredAssessment
from domain.tax.services.rules import rule_book

TOTAL = "TOTAL"


@dataclass(frozen=True)
class AssessedMonth:
    assessment: MonthAssessment
    paid_on: date | None = None


@dataclass(frozen=True)
class TaxYear:
    year: int
    months: list[AssessedMonth]
    foreign: ForeignYear | None
    tax_brl: Decimal
    darf_brl: Decimal
    open_darf_brl: Decimal  # DARFs of the year not marked as paid
    issues: list[LedgerIssue] = field(default_factory=list)


def compute(
    uow: AbstractUnitOfWork, through: date
) -> tuple[list[MonthAssessment], list[ForeignYear], list[LedgerIssue]]:
    sales: list[Sale] = []
    issues: list[LedgerIssue] = []
    for asset in uow.assets.list_all(active_only=False):
        found, problems = realized_sales(asset)
        sales.extend(found)
        issues.extend(problems)
    book = rule_book(uow.tax_rules.list_all())
    return (
        assess_months(sales, book, through=through),
        assess_foreign(sales, book, through=through),
        issues,
    )


def _stored(months: list[MonthAssessment], at: datetime) -> list[StoredAssessment]:
    rows: list[StoredAssessment] = []
    for m in months:
        for c in m.categories:
            rows.append(
                StoredAssessment(
                    m.month,
                    c.category.value,
                    c.sales_brl,
                    c.result_brl,
                    c.loss_out_brl,
                    c.taxable_brl,
                    c.tax_brl,
                    computed_at=at,
                )
            )
        rows.append(
            StoredAssessment(
                m.month,
                TOTAL,
                sum((c.sales_brl for c in m.categories), Decimal("0")),
                sum((c.result_brl for c in m.categories), Decimal("0")),
                Decimal("0"),
                sum((c.taxable_brl for c in m.categories), Decimal("0")),
                m.tax_brl,
                darf_brl=m.darf_brl,
                computed_at=at,
            )
        )
    return rows


def parse_month(text: str) -> date:
    try:
        year, month = (int(p) for p in text.split("-"))
        return date(year, month, 1)
    except ValueError as exc:
        raise ValidationError("Month must be YYYY-MM", code="INVALID_MONTH") from exc


class MonthlyTaxHandler:
    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def _assess(
        self, through: date
    ) -> tuple[list[MonthAssessment], list[ForeignYear], list[LedgerIssue], dict[date, date]]:
        with self.uow_factory() as uow:
            months, foreign, issues = compute(uow, through)
            uow.tax_assessments.save_computed(_stored(months, datetime.now(UTC)))
            uow.commit()
            paid = uow.tax_assessments.paid_months()
        return months, foreign, issues, paid

    def year(self, year: int, *, today: date | None = None) -> TaxYear:
        on = today or date.today()
        if year < 2000 or year > on.year:
            raise ValidationError(f"Year must be between 2000 and {on.year}", code="INVALID_YEAR")
        through = on if year == on.year else date(year, 12, 31)
        months, foreign, issues, paid = self._assess(through)
        mine = [AssessedMonth(m, paid.get(m.month)) for m in months if m.month.year == year]
        darf = sum((m.assessment.darf_brl for m in mine), Decimal("0"))
        open_darf = sum((m.assessment.darf_brl for m in mine if m.paid_on is None), Decimal("0"))
        return TaxYear(
            year=year,
            months=mine,
            foreign=next((f for f in foreign if f.year == year), None),
            tax_brl=sum((m.assessment.tax_brl for m in mine), Decimal("0")),
            darf_brl=darf,
            open_darf_brl=open_darf,
            issues=[i for i in issues if i.on.year == year],
        )

    def month(self, month_text: str, *, today: date | None = None) -> AssessedMonth:
        month = parse_month(month_text)
        on = today or date.today()
        if month > on.replace(day=1):
            raise ValidationError("The month has not started yet", code="INVALID_MONTH")
        months, _, _, paid = self._assess(on)
        found = next((m for m in months if m.month == month), None)
        if found is None:
            raise NotFoundError(f"No sale to assess in {month_text}", code="NO_SALES")
        return AssessedMonth(found, paid.get(month))

    def set_paid(self, month_text: str, paid_on: date | None) -> AssessedMonth:
        month = parse_month(month_text)
        with self.uow_factory() as uow:
            if not uow.tax_assessments.set_paid(month, paid_on):
                raise NotFoundError(f"No assessment of {month_text}", code="NO_SALES")
            uow.commit()
        return self.month(month_text)


def brl_text(value: Decimal) -> str:
    """R$ 1.234,56"""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tax_alerts(months: list[MonthAssessment], paid: dict[date, date], today: date) -> list[Alert]:
    """DARF to pay (or overdue) and an exemption already lost in the current month."""
    alerts: list[Alert] = []
    for m in months:
        if m.darf_brl <= 0 or m.month in paid or m.month >= today.replace(day=1):
            continue
        overdue = today > m.due_date
        label = m.month.strftime("%m/%Y")
        alerts.append(
            Alert(
                f"darf:{m.month.isoformat()}",
                AlertKind.DARF_DUE,
                AlertSeverity.CRITICAL if overdue else AlertSeverity.WARNING,
                f"DARF de {label} {'vencido' if overdue else 'a pagar'}: {brl_text(m.darf_brl)}",
                f"Código 6015, vencimento em {m.due_date.strftime('%d/%m/%Y')}. "
                "Marque como pago na aba Imposto.",
                None,
                f"/carteira/imposto?mes={m.month.strftime('%Y-%m')}",
            )
        )
    current = next((m for m in months if m.month == today.replace(day=1)), None)
    if current is not None and not current.exempt:
        alerts.append(
            Alert(
                f"exemption:{current.month.isoformat()}",
                AlertKind.DARF_DUE,
                AlertSeverity.INFO,
                "Vendas de ações do mês passaram de R$ 20 mil",
                f"Já são {brl_text(current.stock_sales_brl)} vendidos em ações este mês; o lucro "
                "delas deixa de ser isento e entra no DARF.",
                None,
                "/carteira/imposto",
            )
        )
    return alerts
