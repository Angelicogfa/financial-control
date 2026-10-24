"""Immutable domain entities shared across repositories, Unit of Work, services, and handlers.

ORM models in `packages/persistence` are strictly internal to the persistence layer and are mapped
to and from these pure domain entities so that application services, handlers, and controllers
never depend on SQLAlchemy models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fincontrol_core.domain.enums import (
    ArcaClass,
    AssetType,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
    IntraClassStrategy,
    Market,
    SeriesUnit,
    TransactionKind,
    default_arca_class,
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
    id: int | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
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
    cerrado_answers: dict[str, bool] = field(default_factory=dict)
    is_active: bool = True
    notes: str | None = None
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

    @property
    def market(self) -> Market:
        return market_for(self.asset_type)


@dataclass(frozen=True)
class ArcaTargetEntity:
    """Target allocation percentage and intra-class strategy for an ARCA class."""

    arca_class: ArcaClass
    target_pct: Decimal
    intra_class_strategy: IntraClassStrategy = IntraClassStrategy.CERRADO
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.target_pct < Decimal("0") or self.target_pct > Decimal("100"):
            raise ValidationError("target_pct must be between 0 and 100")


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
