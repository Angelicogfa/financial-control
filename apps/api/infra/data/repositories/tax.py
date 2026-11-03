"""SQLAlchemy repository of the tax rule registry.

It takes and returns pure domain entities and never commits
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.tax.entities import TaxRule
from domain.tax.repositories import (
    AbstractTaxAssessmentRepository,
    AbstractTaxRuleRepository,
    StoredAssessment,
)
from infra.data.mappers.tax import to_tax_rule, to_tax_rule_model
from infra.data.models.tax import MonthlyTaxAssessmentModel, TaxRuleModel


class SqlAlchemyTaxRuleRepository(AbstractTaxRuleRepository):
    """SQLAlchemy implementation of AbstractTaxRuleRepository."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> list[TaxRule]:
        stmt = select(TaxRuleModel).order_by(
            TaxRuleModel.regime.asc(), TaxRuleModel.valid_from.asc(), TaxRuleModel.id.asc()
        )
        return [to_tax_rule(m) for m in self.session.scalars(stmt).all()]

    def add(self, rule: TaxRule) -> TaxRule:
        model = to_tax_rule_model(rule)
        self.session.add(model)
        self.session.flush()
        return to_tax_rule(model)


def _assessment(m: MonthlyTaxAssessmentModel) -> StoredAssessment:
    return StoredAssessment(
        month=m.month,
        category=m.category,
        sales_brl=m.sales_brl,
        result_brl=m.result_brl,
        loss_out_brl=m.loss_out_brl,
        taxable_brl=m.taxable_brl,
        tax_brl=m.tax_brl,
        darf_brl=m.darf_brl,
        computed_at=m.computed_at,
        paid_on=m.paid_on,
    )


class SqlAlchemyTaxAssessmentRepository(AbstractTaxAssessmentRepository):
    """Monthly assessments (Phase 48.R7); never commits."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save_computed(self, rows: list[StoredAssessment]) -> None:
        existing = {
            (m.month, m.category): m
            for m in self.session.scalars(select(MonthlyTaxAssessmentModel))
        }
        for row in rows:
            model = existing.get((row.month, row.category))
            if model is None:
                model = MonthlyTaxAssessmentModel(month=row.month, category=row.category)
                self.session.add(model)
            model.sales_brl = row.sales_brl
            model.result_brl = row.result_brl
            model.loss_out_brl = row.loss_out_brl
            model.taxable_brl = row.taxable_brl
            model.tax_brl = row.tax_brl
            model.darf_brl = row.darf_brl
            model.computed_at = row.computed_at
        self.session.flush()

    def list_between(self, start: date, end: date) -> list[StoredAssessment]:
        stmt = (
            select(MonthlyTaxAssessmentModel)
            .where(MonthlyTaxAssessmentModel.month >= start, MonthlyTaxAssessmentModel.month <= end)
            .order_by(MonthlyTaxAssessmentModel.month, MonthlyTaxAssessmentModel.category)
        )
        return [_assessment(m) for m in self.session.scalars(stmt)]

    def paid_months(self) -> dict[date, date]:
        stmt = select(MonthlyTaxAssessmentModel).where(
            MonthlyTaxAssessmentModel.category == "TOTAL",
            MonthlyTaxAssessmentModel.paid_on.is_not(None),
        )
        return {m.month: m.paid_on for m in self.session.scalars(stmt) if m.paid_on}

    def set_paid(self, month: date, paid_on: date | None) -> bool:
        model = self.session.scalars(
            select(MonthlyTaxAssessmentModel).where(
                MonthlyTaxAssessmentModel.month == month,
                MonthlyTaxAssessmentModel.category == "TOTAL",
            )
        ).first()
        if model is None:
            return False
        model.paid_on = paid_on
        self.session.flush()
        return True
