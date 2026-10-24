"""Immutable domain entities shared across repositories, Unit of Work, services, and handlers.

ORM models in `packages/persistence` are strictly internal to the persistence layer and are mapped
to and from these pure domain entities so that application services, handlers, and controllers
never depend on SQLAlchemy models.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fincontrol_core.domain.enums import (
    AccountKind,
    AnswerSource,
    AnswerValue,
    ArcaClass,
    AssetPurpose,
    AssetType,
    ChecklistProfile,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
    JobRunStatus,
    Market,
    SeriesUnit,
    TransactionKind,
    default_arca_class,
    default_checklist_profile,
    default_currency,
    market_for,
)
from fincontrol_core.errors import ValidationError

# Accepted `contracted_rate` range and meaning per indexer (ADR 0006).
CONTRACTED_RATE_BOUNDS: dict[FixedIncomeIndexer, tuple[Decimal, Decimal, str]] = {
    FixedIncomeIndexer.CDI: (
        Decimal("0.5"),
        Decimal("3.0"),
        "a multiplier of the index (1.10 = 110% of CDI)",
    ),
    FixedIncomeIndexer.SELIC: (
        Decimal("0.5"),
        Decimal("3.0"),
        "a multiplier of the index (1.00 = 100% of SELIC)",
    ),
    FixedIncomeIndexer.PRE: (
        Decimal("0"),
        Decimal("0.5"),
        "an annual fraction (0.12 = 12% a.a.)",
    ),
    FixedIncomeIndexer.IPCA: (
        Decimal("0"),
        Decimal("0.5"),
        "an annual real-rate fraction (0.065 = IPCA + 6.5% a.a.)",
    ),
}


@dataclass(frozen=True)
class FixedIncomeTermEntity:
    """Contract terms for automatic fixed income valuation along the indexer curve."""

    instrument_kind: FixedIncomeInstrumentKind
    indexer: FixedIncomeIndexer
    contracted_rate: Decimal
    issue_date: date
    maturity_date: date | None = None
    tax_exempt: bool = False
    liquidity: FixedIncomeLiquidity = FixedIncomeLiquidity.AT_MATURITY
    issuer: str | None = None
    id: int | None = None
    asset_id: int | None = None

    def __post_init__(self) -> None:
        low, high, meaning = CONTRACTED_RATE_BOUNDS[self.indexer]
        if not low <= self.contracted_rate <= high:
            raise ValidationError(
                f"contracted_rate {self.contracted_rate} is outside [{low}, {high}] for "
                f"{self.indexer.value}: it must be {meaning} (ADR 0006)",
                code="INVALID_CONTRACTED_RATE",
            )


@dataclass(frozen=True)
class TransactionEntity:
    """Pure domain representation of a buy or sell trade."""

    asset_id: int
    kind: TransactionKind
    trade_date: date
    quantity: Decimal
    unit_price: Decimal
    fees: Decimal = Decimal("0")
    fx_rate: Decimal = Decimal("1")
    notes: str | None = None
    account_id: int | None = None
    id: int | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.quantity <= Decimal("0"):
            raise ValidationError("quantity must be positive")
        if self.unit_price < Decimal("0"):
            raise ValidationError("unit_price cannot be negative")
        if self.fees < Decimal("0"):
            raise ValidationError("fees cannot be negative")
        if self.fx_rate <= Decimal("0"):
            raise ValidationError("fx_rate must be positive")


@dataclass(frozen=True)
class EarningEntity:
    """Pure domain representation of received dividends, JCP, FII yields, or coupons."""

    asset_id: int
    kind: EarningKind
    payment_date: date
    gross_amount: Decimal
    withholding_tax: Decimal = Decimal("0")
    net_amount: Decimal | None = None
    ex_date: date | None = None
    notes: str | None = None
    fx_rate: Decimal = Decimal("1")
    account_id: int | None = None
    id: int | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.fx_rate <= Decimal("0"):
            raise ValidationError("fx_rate must be positive")
        if self.gross_amount <= Decimal("0"):
            raise ValidationError("gross_amount must be positive")
        if self.withholding_tax < Decimal("0"):
            raise ValidationError("withholding_tax cannot be negative")
        resolved_net = (
            self.net_amount
            if self.net_amount is not None
            else self.gross_amount - self.withholding_tax
        )
        if resolved_net < Decimal("0"):
            raise ValidationError("net_amount cannot be negative")
        object.__setattr__(self, "net_amount", resolved_net)


@dataclass(frozen=True)
class ChecklistAnswer:
    """One recorded checklist answer; the history is append-only (item 11.4).

    `value=None` records that a previous answer was cleared (the question is pending again).
    """

    question_id: str
    value: AnswerValue | None
    source: AnswerSource = AnswerSource.MANUAL
    evidence: str | None = None
    answered_at: datetime | None = None
    checklist_version: int = 2
    id: int | None = None

    @classmethod
    def coerce(cls, question_id: str, raw: object) -> ChecklistAnswer:
        """Accept a ChecklistAnswer, an AnswerValue/str, a legacy bool or None."""
        if isinstance(raw, ChecklistAnswer):
            return raw
        if raw is None:
            return cls(question_id, None)
        if isinstance(raw, bool):
            return cls(question_id, AnswerValue.YES if raw else AnswerValue.NO)
        try:
            return cls(question_id, AnswerValue(str(raw).upper()))
        except ValueError as exc:
            raise ValidationError(f"Invalid answer for {question_id}: {raw!r}") from exc

    @property
    def as_bool(self) -> bool | None:
        if self.value == AnswerValue.YES:
            return True
        if self.value == AnswerValue.NO:
            return False
        return None


@dataclass(frozen=True)
class AssetEntity:
    """Pure domain representation of an investment asset and its optional children."""

    ticker: str
    name: str
    asset_type: AssetType
    arca_class: ArcaClass | None = None
    currency: str | None = None
    manual_price: Decimal | None = None
    custom_class_weight: Decimal | None = None
    use_cerrado: bool = True
    # Current answer per question (latest of the append-only history). Plain bools and
    # AnswerValue strings are accepted and normalized to ChecklistAnswer.
    cerrado_answers: Mapping[str, Any] = field(default_factory=dict)
    is_active: bool = True
    notes: str | None = None
    purpose: AssetPurpose = AssetPurpose.ARCA
    checklist_profile: ChecklistProfile | None = None
    fixed_income_term: FixedIncomeTermEntity | None = None
    transactions: tuple[TransactionEntity, ...] = ()
    earnings: tuple[EarningEntity, ...] = ()
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        normalized_ticker = self.ticker.strip().upper()
        if not normalized_ticker:
            raise ValidationError("ticker cannot be empty")
        object.__setattr__(self, "ticker", normalized_ticker)
        object.__setattr__(self, "name", self.name.strip())
        if self.arca_class is None:
            object.__setattr__(self, "arca_class", default_arca_class(self.asset_type))
        if self.currency is None:
            object.__setattr__(self, "currency", default_currency(self.asset_type))
        else:
            object.__setattr__(self, "currency", self.currency.strip().upper())
        if self.manual_price is not None and self.manual_price < Decimal("0"):
            raise ValidationError("manual_price cannot be negative")
        if self.custom_class_weight is not None and self.custom_class_weight < Decimal("0"):
            raise ValidationError("custom_class_weight cannot be negative")
        answers = {
            qid: ChecklistAnswer.coerce(qid, raw) for qid, raw in self.cerrado_answers.items()
        }
        object.__setattr__(
            self, "cerrado_answers", {q: a for q, a in answers.items() if a.value is not None}
        )

    @property
    def market(self) -> Market:
        return market_for(self.asset_type)

    @property
    def profile(self) -> ChecklistProfile:
        """Chosen checklist profile, or the default one for the asset type."""
        return self.checklist_profile or default_checklist_profile(self.asset_type)


@dataclass(frozen=True)
class MarketSeriesPoint:
    """Single historical price or macroeconomic benchmark data point."""

    symbol: str
    reference_date: date
    value: float
    unit: SeriesUnit | None = None
    id: int | None = None


@dataclass(frozen=True)
class PortfolioSnapshotEntity:
    """Daily consolidated portfolio snapshot entity."""

    snapshot_date: date
    invested_value: float
    market_value: float
    unrealized_pnl: float
    realized_pnl_cum: float = 0.0
    earnings_cum: float = 0.0
    consolidated_pnl: float = 0.0
    net_flow: float = 0.0
    by_class: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JobRunEntity:
    """One execution of a background job (worker freshness and audit trail)."""

    job_name: str
    started_at: datetime
    status: JobRunStatus = JobRunStatus.RUNNING
    attempts: int = 0
    finished_at: datetime | None = None
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    id: int | None = None


@dataclass(frozen=True)
class AccountEntity:
    """A custody account (broker, bank, exchange) where trades and earnings happen."""

    name: str
    institution: str | None = None
    kind: AccountKind = AccountKind.BROKER
    is_active: bool = True
    id: int | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        normalized = self.name.strip()
        if not normalized:
            raise ValidationError("account name cannot be empty")
        object.__setattr__(self, "name", normalized)


@dataclass(frozen=True)
class ChecklistEvaluationRecord:
    """Stored result of a checklist evaluation, kept to chart the score over time."""

    asset_id: int
    evaluated_at: datetime
    profile: ChecklistProfile
    score: int
    normalized_score: float | None
    coverage_pct: float
    answered: int
    applicable: int
    recommendation: str
    checklist_version: int = 2
    id: int | None = None

    def same_result(self, other: ChecklistEvaluationRecord) -> bool:
        """Whether two evaluations reached the same outcome (used to skip duplicates)."""
        return (
            self.profile == other.profile
            and self.score == other.score
            and self.answered == other.answered
            and self.applicable == other.applicable
            and self.recommendation == other.recommendation
        )
