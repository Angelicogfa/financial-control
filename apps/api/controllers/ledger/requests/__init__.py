"""Pydantic request/response DTOs for the ledger module.

Scope: transactions, earnings, corporate events and B3 statement imports.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from domain.shared.enums import (
    ArcaClass,
    AssetType,
    CorporateEventKind,
    EarningKind,
    FixedIncomeIndexer,
    FixedIncomeInstrumentKind,
    FixedIncomeLiquidity,
    TransactionKind,
)


class TransactionCreateRequest(BaseModel):
    """Payload to record a buy or sell trade."""

    asset_id: int
    kind: TransactionKind
    trade_date: date
    quantity: Decimal = Field(..., gt=Decimal("0"))
    unit_price: Decimal = Field(..., ge=Decimal("0"))
    fees: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    fx_rate: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    notes: str | None = None
    account_id: int | None = None


class TransactionUpdateRequest(BaseModel):
    """Payload to correct a recorded trade (the asset cannot change)."""

    kind: TransactionKind
    trade_date: date
    quantity: Decimal = Field(..., gt=Decimal("0"))
    unit_price: Decimal = Field(..., ge=Decimal("0"))
    fees: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    fx_rate: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    notes: str | None = None
    account_id: int | None = None


class TransactionResponseDTO(BaseModel):
    """Serialized Transaction domain entity."""

    id: int
    asset_id: int
    ticker: str | None = None
    kind: TransactionKind
    trade_date: date
    quantity: float
    unit_price: float
    fees: float
    fx_rate: float
    total_brl: float
    notes: str | None = None
    account_id: int | None = None
    created_at: datetime | None = None


class EarningCreateRequest(BaseModel):
    """Payload to record received dividends, JCP, FII yields, or fixed income coupons."""

    asset_id: int
    kind: EarningKind
    payment_date: date
    gross_amount: Decimal = Field(..., gt=Decimal("0"))
    withholding_tax: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    net_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    ex_date: date | None = None
    notes: str | None = None
    fx_rate: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    account_id: int | None = None


class EarningUpdateRequest(BaseModel):
    """Payload to correct a recorded earning (the asset cannot change)."""

    kind: EarningKind
    payment_date: date
    gross_amount: Decimal = Field(..., gt=Decimal("0"))
    withholding_tax: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    net_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    ex_date: date | None = None
    notes: str | None = None
    fx_rate: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    account_id: int | None = None


class EarningResponseDTO(BaseModel):
    """Serialized Earning domain entity."""

    id: int
    asset_id: int
    ticker: str | None = None
    kind: EarningKind
    payment_date: date
    ex_date: date | None = None
    gross_amount: float
    withholding_tax: float
    net_amount: float
    fx_rate: float = 1.0
    net_amount_brl: float = 0.0
    notes: str | None = None
    account_id: int | None = None
    created_at: datetime | None = None


class ImportLineDTO(BaseModel):
    line_no: int
    action: str
    status: str
    entry_date: date | None = None
    ticker: str | None = None
    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    trade_kind: str | None = None
    earning_kind: str | None = None
    event_kind: str | None = None
    note: str = ""


class ImportFixedIncomeTermDTO(BaseModel):
    """Contract terms of a Treasury bond or bank security registered with the import.

    The preview suggests what the statement tells (kind, issuer, first date, and the
    maturity from the Treasury catalog); the contracted rate is never in a B3 statement.
    """

    instrument_kind: FixedIncomeInstrumentKind
    indexer: FixedIncomeIndexer
    contracted_rate: Decimal | None = Field(
        default=None,
        description=(
            "ADR 0006: multiplier for CDI/SELIC (1.10 = 110% of CDI); "
            "annual fraction for PRE/IPCA (0.065 = 6.5% a.a.). Required to register."
        ),
    )
    issue_date: date | None = Field(
        default=None, description="Defaults to the first date of the security in the statement"
    )
    maturity_date: date | None = None
    tax_exempt: bool = False
    liquidity: FixedIncomeLiquidity = FixedIncomeLiquidity.AT_MATURITY
    issuer: str | None = None


class UnknownTickerDTO(BaseModel):
    ticker: str
    name: str | None = None
    asset_type: AssetType | None = None
    arca_class: ArcaClass | None = Field(
        default=None, description="Suggested ARCA quadrant (known once the type is known)"
    )
    fixed_income_term: ImportFixedIncomeTermDTO | None = Field(
        default=None,
        description="Treasury bond or bank security: terms to confirm (rate still missing)",
    )


class ImportNewAssetRequest(BaseModel):
    """An unknown ticker to register with the import, as the research flow would.

    Treasury bonds and bank securities carry `fixed_income_term` with the contracted rate.
    """

    ticker: str = Field(..., min_length=1, max_length=32)
    asset_type: AssetType | None = None
    arca_class: ArcaClass | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    fixed_income_term: ImportFixedIncomeTermDTO | None = None


class ImportPreviewDTO(BaseModel):
    kind: str
    counts: dict[str, int]
    unknown_tickers: list[UnknownTickerDTO]
    lines: list[ImportLineDTO]


class ImportCommitDTO(BaseModel):
    kind: str
    created: dict[str, int]
    skipped: dict[str, int]
    created_assets: list[str] = Field(default_factory=list)


class CorporateEventRequest(BaseModel):
    """Split (factor 2 for 1:2), reverse split (0.1 for 10:1) or bonus (1.1 for 10%)."""

    asset_id: int
    kind: CorporateEventKind
    ex_date: date
    factor: Decimal = Field(..., gt=Decimal("0"))
    unit_cost: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    notes: str | None = None


class CorporateEventDTO(CorporateEventRequest):
    id: int
    ticker: str | None = None
    imported: bool = False
