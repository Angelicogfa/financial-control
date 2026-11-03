"""Repository ports of the tax rule registry and of the monthly assessments (Phase 48.R7)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

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


@dataclass(frozen=True)
class StoredAssessment:
    """One month and category of the assessment as last computed; `TOTAL` carries the DARF."""

    month: date
    category: str
    sales_brl: Decimal
    result_brl: Decimal
    loss_out_brl: Decimal
    taxable_brl: Decimal
    tax_brl: Decimal
    darf_brl: Decimal = Decimal("0")
    computed_at: datetime | None = None
    paid_on: date | None = None


class AbstractTaxAssessmentRepository(ABC):
    @abstractmethod
    def save_computed(self, rows: list[StoredAssessment]) -> None:
        """Upsert by (month, category), keeping the DARF payment date already recorded."""

    @abstractmethod
    def list_between(self, start: date, end: date) -> list[StoredAssessment]: ...

    @abstractmethod
    def paid_months(self) -> dict[date, date]:
        """Month -> the day its DARF was paid."""

    @abstractmethod
    def set_paid(self, month: date, paid_on: date | None) -> bool:
        """False when the month was never assessed."""
