"""SQLAlchemy repository of the tax rule registry.

It takes and returns pure domain entities and never commits
(the transaction boundary belongs to `SqlAlchemyUnitOfWork`)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.tax.entities import TaxRule
from domain.tax.repositories import AbstractTaxRuleRepository
from infra.data.mappers.tax import to_tax_rule, to_tax_rule_model
from infra.data.models.tax import TaxRuleModel


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
