"""Repository port of the tax rule registry."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.tax.entities import TaxRule


class AbstractTaxRuleRepository(ABC):
    """Tax rules with validity periods; a legal change is a new record."""

    @abstractmethod
    def list_all(self) -> list[TaxRule]:
        """Every rule, ordered by regime and start of validity."""
        raise NotImplementedError

    @abstractmethod
    def add(self, rule: TaxRule) -> TaxRule:
        raise NotImplementedError
