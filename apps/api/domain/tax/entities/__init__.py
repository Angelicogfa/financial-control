"""Tax rules with validity periods (vigência): a legal change becomes a new record.

Conventions (ADR 0006):
- Rates are fractions (0.225 = 22.5%).
- A bracket covers holding periods up to `up_to_days` calendar days (inclusive); the last
  bracket of a rule has `up_to_days=None` (no upper bound). Rules that do not depend on the
  holding period (stocks, JCP, foreign assets) have a single open bracket.
- `valid_from`/`valid_to` are inclusive. The rule that applies to a taxable event is the one
  in force on the event date (the redemption, sale or payment date).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from core.errors import NotFoundError, ValidationError


class TaxKind(StrEnum):
    """Which tax a rule describes."""

    INCOME_TAX = "INCOME_TAX"
    IOF = "IOF"


class TaxRegime(StrEnum):
    """Tax treatment of an income or gain for an individual (pessoa física) in Brazil."""

    FIXED_INCOME_REGRESSIVE = "FIXED_INCOME_REGRESSIVE"
    FIXED_INCOME_EXEMPT = "FIXED_INCOME_EXEMPT"
    IOF_REGRESSIVE = "IOF_REGRESSIVE"
    STOCK_SWING_TRADE = "STOCK_SWING_TRADE"
    ETF_BDR_SWING_TRADE = "ETF_BDR_SWING_TRADE"
    FII_CAPITAL_GAIN = "FII_CAPITAL_GAIN"
    FII_DISTRIBUTION = "FII_DISTRIBUTION"
    DIVIDEND_WITHHOLDING = "DIVIDEND_WITHHOLDING"
    JCP_WITHHOLDING = "JCP_WITHHOLDING"
    FOREIGN_ANNUAL = "FOREIGN_ANNUAL"
    CRYPTO_CAPITAL_GAIN = "CRYPTO_CAPITAL_GAIN"


class TaxRuleNotFoundError(NotFoundError):
    """No rule of the requested regime is registered."""


@dataclass(frozen=True)
class TaxBracket:
    """Rate applied to holding periods up to `up_to_days` calendar days (None = no bound)."""

    up_to_days: int | None
    rate: float

    def covers(self, calendar_days: int) -> bool:
        return self.up_to_days is None or calendar_days <= self.up_to_days


@dataclass(frozen=True)
class NextBracket:
    """Bracket reached after holding the position for `from_days` calendar days."""

    from_days: int
    rate: float


@dataclass(frozen=True)
class TaxRule:
    """Rates of one tax regime in force between `valid_from` and `valid_to` (inclusive)."""

    regime: TaxRegime
    tax_kind: TaxKind
    brackets: tuple[TaxBracket, ...]
    valid_from: date
    valid_to: date | None = None
    legal_basis: str = ""
    description: str = ""
    id: int | None = None

    def __post_init__(self) -> None:
        if not self.brackets:
            raise ValidationError(
                f"Tax rule {self.regime.value} needs at least one bracket", code="INVALID_TAX_RULE"
            )
        bounds = [b.up_to_days for b in self.brackets]
        if bounds[-1] is not None or any(b is None for b in bounds[:-1]):
            raise ValidationError(
                f"Only the last bracket of {self.regime.value} may be open-ended",
                code="INVALID_TAX_RULE",
            )
        closed = [b for b in bounds if b is not None]
        if closed != sorted(set(closed)) or any(b < 0 for b in closed):
            raise ValidationError(
                f"Brackets of {self.regime.value} must have increasing day limits",
                code="INVALID_TAX_RULE",
            )
        if any(not 0.0 <= b.rate <= 1.0 for b in self.brackets):
            raise ValidationError(
                f"Rates of {self.regime.value} must be fractions in [0, 1]",
                code="INVALID_TAX_RULE",
            )
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValidationError(
                f"Rule {self.regime.value} ends before it starts", code="INVALID_TAX_RULE"
            )

    def in_force_on(self, day: date) -> bool:
        return self.valid_from <= day and (self.valid_to is None or day <= self.valid_to)

    def rate_for(self, calendar_days: int) -> float:
        """Rate for a holding period of `calendar_days` (negative periods use the first)."""
        days = max(0, calendar_days)
        return next(b.rate for b in self.brackets if b.covers(days))

    def next_bracket(self, calendar_days: int) -> NextBracket | None:
        """First bracket after the current one whose rate differs, if any."""
        days = max(0, calendar_days)
        current = self.rate_for(days)
        for previous, bracket in zip(self.brackets, self.brackets[1:], strict=False):
            limit = previous.up_to_days
            if limit is not None and limit >= days and bracket.rate != current:
                return NextBracket(from_days=limit + 1, rate=bracket.rate)
        return None

    @property
    def is_holding_period_based(self) -> bool:
        return len(self.brackets) > 1


class TaxRuleBook:
    """All registered rules, resolved by regime and the date of the taxable event.

    Dates before the first rule of a regime fall back to that first rule, so historical
    ledgers keep a defined rate even when the registry starts at the current legislation.
    """

    def __init__(self, rules: Iterable[TaxRule]) -> None:
        by_regime: dict[TaxRegime, list[TaxRule]] = {}
        for rule in rules:
            by_regime.setdefault(rule.regime, []).append(rule)
        for regime, items in by_regime.items():
            items.sort(key=lambda r: r.valid_from)
            for before, after in zip(items, items[1:], strict=False):
                if before.valid_to is None or before.valid_to >= after.valid_from:
                    raise ValidationError(
                        f"Rules of {regime.value} overlap: {before.valid_from} and "
                        f"{after.valid_from}",
                        code="OVERLAPPING_TAX_RULES",
                    )
        self._by_regime = by_regime

    @property
    def rules(self) -> tuple[TaxRule, ...]:
        return tuple(rule for items in self._by_regime.values() for rule in items)

    def has(self, regime: TaxRegime) -> bool:
        return regime in self._by_regime

    def rule(self, regime: TaxRegime, on: date) -> TaxRule:
        items = self._by_regime.get(regime)
        if not items:
            raise TaxRuleNotFoundError(f"No tax rule registered for {regime.value}")
        for rule in items:
            if rule.in_force_on(on):
                return rule
        if on < items[0].valid_from:
            return items[0]
        # A gap between two records (or after an ended rule) keeps the last rule in force.
        return max((r for r in items if r.valid_from <= on), key=lambda r: r.valid_from)

    def rate(self, regime: TaxRegime, calendar_days: int, on: date) -> float:
        return self.rule(regime, on).rate_for(calendar_days)
