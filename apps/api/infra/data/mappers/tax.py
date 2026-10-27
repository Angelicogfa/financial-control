"""Mapping between the tax rule ORM model and the pure domain entity."""

from __future__ import annotations

from domain.tax.entities import TaxBracket, TaxKind, TaxRegime, TaxRule
from infra.data.models.tax import TaxRuleModel


def to_tax_rule(model: TaxRuleModel) -> TaxRule:
    return TaxRule(
        regime=TaxRegime(model.regime),
        tax_kind=TaxKind(model.tax_kind),
        brackets=tuple(
            TaxBracket(item.get("up_to_days"), float(item["rate"])) for item in model.brackets
        ),
        valid_from=model.valid_from,
        valid_to=model.valid_to,
        legal_basis=model.legal_basis,
        description=model.description,
        id=model.id,
    )


def to_tax_rule_model(rule: TaxRule) -> TaxRuleModel:
    return TaxRuleModel(
        regime=rule.regime.value,
        tax_kind=rule.tax_kind.value,
        brackets=[{"up_to_days": b.up_to_days, "rate": b.rate} for b in rule.brackets],
        valid_from=rule.valid_from,
        valid_to=rule.valid_to,
        legal_basis=rule.legal_basis,
        description=rule.description,
    )
