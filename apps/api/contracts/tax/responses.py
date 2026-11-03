"""Pydantic response DTOs for the tax module.

Scope: tax rule registry, per-asset tax status and the fixed income comparator.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from domain.shared.enums import AssetType
from domain.tax.entities import TaxKind, TaxRegime
from domain.tax.services.comparator import OfferIndexer


class TaxBracketDTO(BaseModel):
    up_to_days: int | None
    rate: float


class TaxRuleDTO(BaseModel):
    id: int | None = None
    regime: TaxRegime
    tax_kind: TaxKind
    brackets: list[TaxBracketDTO]
    valid_from: date
    valid_to: date | None = None
    legal_basis: str
    description: str


class TaxRegimeInfoDTO(BaseModel):
    regime: TaxRegime
    tax_kind: TaxKind
    current_rate: float
    brackets: list[TaxBracketDTO]
    valid_from: date
    valid_to: date | None = None
    legal_basis: str
    description: str


class LotTaxStatusDTO(BaseModel):
    start_date: date
    principal: float
    gross_value: float
    gross_yield: float
    holding_days: int
    income_tax_rate: float
    iof_rate: float
    iof_due: float
    iof_free_date: date | None = None
    income_tax_due: float
    net_value: float
    next_bracket_date: date | None = None
    days_to_next_bracket: int | None = None
    next_income_tax_rate: float | None = None
    projected_gross_at_next_bracket: float | None = None
    tax_at_next_bracket: float | None = None
    tax_saving_by_waiting: float | None = None
    net_gain_by_waiting: float | None = None


class AssetTaxStatusDTO(BaseModel):
    asset_id: int | None
    ticker: str
    asset_type: AssetType
    as_of_date: date
    is_fixed_income: bool
    tax_exempt: bool
    regimes: list[TaxRegimeInfoDTO]
    lots: list[LotTaxStatusDTO]
    invested_principal: float
    gross_value: float
    iof_due: float
    income_tax_due: float
    net_value: float
    next_bracket_date: date | None = None
    tax_saving_by_waiting: float


class RateScenarioDTO(BaseModel):
    name: str
    annual_cdi_rate: float
    annual_ipca_rate: float


class ResolvedOfferDTO(BaseModel):
    label: str
    asset_id: int | None = None
    indexer: OfferIndexer
    rate: float
    term_days: int
    tax_exempt: bool
    grace_days: int


class OfferOutcomeDTO(BaseModel):
    days: int
    redemption_date: date
    business_days: int
    redeemable: bool
    gross_value: float
    gross_yield: float
    iof: float
    income_tax_rate: float
    income_tax: float
    net_value: float
    net_yield: float
    gross_annual_rate: float
    net_annual_rate: float


class EquivalentRateDTO(BaseModel):
    up_to_days: int | None
    income_tax_rate: float
    exempt_equivalent_rate: float
    taxed_equivalent_rate: float


class OfferProjectionDTO(BaseModel):
    label: str
    scenario: str
    gross_annual_rate: float
    at_maturity: OfferOutcomeDTO
    at_common_window: OfferOutcomeDTO
    equivalent_rates: list[EquivalentRateDTO]


class BreakEvenDTO(BaseModel):
    scenario: str
    first: str
    second: str
    winner: str | None = None
    break_even_days: int | None = None
    always_ahead: bool


class FixedIncomeComparisonDTO(BaseModel):
    as_of_date: date
    principal: float
    common_window_days: int
    offers: list[ResolvedOfferDTO]
    scenarios: list[RateScenarioDTO]
    projections: list[OfferProjectionDTO]
    break_evens: list[BreakEvenDTO]
    best_by_scenario: dict[str, str]


class TaxCategoryMonthDTO(BaseModel):
    """One category of a month: COMMON, DAY_TRADE or FII (Phase 48.R7)."""

    category: str
    sales_brl: float
    result_brl: float = Field(description="Gains minus losses, exempt gains left out")
    exempt_gain_brl: float
    loss_in_brl: float
    loss_used_brl: float
    loss_out_brl: float
    taxable_brl: float
    rate: float
    tax_brl: float


class TaxSaleDTO(BaseModel):
    asset_id: int
    ticker: str
    on: date
    quantity: float
    sale_value_brl: float
    cost_brl: float
    fees_brl: float
    gain_brl: float
    day_trade: bool
    category: str


class TaxMonthDTO(BaseModel):
    month: str = Field(description="YYYY-MM")
    categories: list[TaxCategoryMonthDTO]
    stock_sales_brl: float
    exempt: bool = Field(description="Ações sales of the month up to R$ 20 thousand")
    tax_brl: float
    withheld_brl: float
    withheld_credit_in_brl: float
    withheld_credit_out_brl: float
    carried_darf_in_brl: float
    darf_brl: float = Field(description="To pay by DARF 6015 (0 below R$ 10, carried)")
    carried_darf_out_brl: float
    due_date: date
    darf_code: str = "6015"
    paid_on: date | None = None
    sales: list[TaxSaleDTO] = Field(default_factory=list)


class ForeignTaxYearDTO(BaseModel):
    year: int
    sales_brl: float
    result_brl: float
    loss_in_brl: float
    loss_out_brl: float
    taxable_brl: float
    rate: float
    tax_brl: float


class TaxLedgerIssueDTO(BaseModel):
    ticker: str
    on: date
    message: str


class TaxYearDTO(BaseModel):
    """The monthly income tax of a year (Phase 48.R7): what was due and what is still open."""

    year: int
    months: list[TaxMonthDTO]
    foreign: ForeignTaxYearDTO | None = None
    tax_brl: float
    darf_brl: float
    open_darf_brl: float
    issues: list[TaxLedgerIssueDTO] = Field(default_factory=list)
