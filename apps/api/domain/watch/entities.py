"""What the investor watches (Phase 48.R6): alert rules on any ticker and a thesis per asset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class RuleMetric(StrEnum):
    PRICE = "PRICE"  # last stored quote, or the close of the B3 catalog
    DIVIDEND_YIELD = "DIVIDEND_YIELD"  # fraction (0.08 = 8%)
    PRICE_TO_EARNINGS = "PRICE_TO_EARNINGS"
    PRICE_TO_BOOK = "PRICE_TO_BOOK"


class RuleOperator(StrEnum):
    ABOVE = "ABOVE"  # value >= threshold
    BELOW = "BELOW"  # value <= threshold


METRIC_LABELS: dict[RuleMetric, str] = {
    RuleMetric.PRICE: "Preço",
    RuleMetric.DIVIDEND_YIELD: "Dividend yield",
    RuleMetric.PRICE_TO_EARNINGS: "P/L",
    RuleMetric.PRICE_TO_BOOK: "P/VP",
}


@dataclass(frozen=True)
class AlertRule:
    ticker: str
    metric: RuleMetric
    operator: RuleOperator
    threshold: Decimal
    is_active: bool = True
    note: str | None = None
    created_at: datetime | None = None
    # Written by the worker (job evaluate_alert_rules): the last value read and when the
    # condition last became true (None while it is false).
    last_value: Decimal | None = None
    last_checked_at: datetime | None = None
    triggered_at: datetime | None = None
    id: int | None = None


@dataclass(frozen=True)
class RuleReading:
    """A rule against the database now: the value (None without data) and whether it holds."""

    rule: AlertRule
    value: float | None
    triggered: bool


@dataclass(frozen=True)
class AssetNote:
    """A line of the investment thesis: what was thought, and when to look at it again."""

    asset_id: int
    written_on: date
    text: str
    review_at: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: int | None = None

    def due(self, today: date) -> bool:
        return self.review_at is not None and self.review_at <= today
