"""Map pure tax domain results to response DTOs."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

from contracts.tax.responses import (
    AssetTaxStatusDTO,
    BreakEvenDTO,
    FixedIncomeComparisonDTO,
    ForeignTaxYearDTO,
    OfferProjectionDTO,
    RateScenarioDTO,
    ResolvedOfferDTO,
    TaxCategoryMonthDTO,
    TaxLedgerIssueDTO,
    TaxMonthDTO,
    TaxRuleDTO,
    TaxSaleDTO,
    TaxYearDTO,
)
from domain.tax.assessment import MonthAssessment
from domain.tax.entities import TaxRule
from domain.tax.services.comparator import FixedIncomeComparison, FixedIncomeOffer
from domain.tax.services.monthly import AssessedMonth, TaxYear
from domain.tax.services.status import AssetTaxStatus


def to_tax_rule_dto(rule: TaxRule) -> TaxRuleDTO:
    return TaxRuleDTO(**asdict(rule))


def to_asset_tax_status_dto(status: AssetTaxStatus) -> AssetTaxStatusDTO:
    return AssetTaxStatusDTO(**asdict(status))


def to_comparison_dto(
    comparison: FixedIncomeComparison,
    offers: list[FixedIncomeOffer],
    asset_ids: list[int | None],
) -> FixedIncomeComparisonDTO:
    return FixedIncomeComparisonDTO(
        as_of_date=comparison.as_of_date,
        principal=comparison.principal,
        common_window_days=comparison.common_window_days,
        offers=[
            ResolvedOfferDTO(**asdict(offer), asset_id=asset_id)
            for offer, asset_id in zip(offers, asset_ids, strict=True)
        ],
        scenarios=[RateScenarioDTO(**asdict(s)) for s in comparison.scenarios],
        projections=[OfferProjectionDTO(**asdict(p)) for p in comparison.projections],
        break_evens=[BreakEvenDTO(**asdict(b)) for b in comparison.break_evens],
        best_by_scenario=dict(comparison.best_by_scenario),
    )


def _month_dto(m: MonthAssessment, paid_on: date | None, *, with_sales: bool) -> TaxMonthDTO:
    return TaxMonthDTO(
        month=m.month.strftime("%Y-%m"),
        categories=[
            TaxCategoryMonthDTO(
                category=c.category.value,
                sales_brl=float(c.sales_brl),
                result_brl=float(c.result_brl),
                exempt_gain_brl=float(c.exempt_gain_brl),
                loss_in_brl=float(c.loss_in_brl),
                loss_used_brl=float(c.loss_used_brl),
                loss_out_brl=float(c.loss_out_brl),
                taxable_brl=float(c.taxable_brl),
                rate=float(c.rate),
                tax_brl=float(c.tax_brl),
            )
            for c in m.categories
        ],
        stock_sales_brl=float(m.stock_sales_brl),
        exempt=m.exempt,
        tax_brl=float(m.tax_brl),
        withheld_brl=float(m.withheld_brl),
        withheld_credit_in_brl=float(m.withheld_credit_in_brl),
        withheld_credit_out_brl=float(m.withheld_credit_out_brl),
        carried_darf_in_brl=float(m.carried_darf_in_brl),
        darf_brl=float(m.darf_brl),
        carried_darf_out_brl=float(m.carried_darf_out_brl),
        due_date=m.due_date,
        paid_on=paid_on,
        sales=[
            TaxSaleDTO(
                asset_id=s.asset_id,
                ticker=s.ticker,
                on=s.on,
                quantity=float(s.quantity),
                sale_value_brl=round(float(s.sale_value_brl), 2),
                cost_brl=round(float(s.cost_brl), 2),
                fees_brl=round(float(s.fees_brl), 2),
                gain_brl=round(float(s.gain_brl), 2),
                day_trade=s.day_trade,
                category=s.category.value,
            )
            for s in m.sales
        ]
        if with_sales
        else [],
    )


def to_tax_month_dto(month: AssessedMonth) -> TaxMonthDTO:
    return _month_dto(month.assessment, month.paid_on, with_sales=True)


def to_tax_year_dto(year: TaxYear) -> TaxYearDTO:
    f = year.foreign
    return TaxYearDTO(
        year=year.year,
        months=[_month_dto(m.assessment, m.paid_on, with_sales=False) for m in year.months],
        foreign=ForeignTaxYearDTO(
            year=f.year,
            sales_brl=float(f.sales_brl),
            result_brl=float(f.result_brl),
            loss_in_brl=float(f.loss_in_brl),
            loss_out_brl=float(f.loss_out_brl),
            taxable_brl=float(f.taxable_brl),
            rate=float(f.rate),
            tax_brl=float(f.tax_brl),
        )
        if f
        else None,
        tax_brl=float(year.tax_brl),
        darf_brl=float(year.darf_brl),
        open_darf_brl=float(year.open_darf_brl),
        issues=[
            TaxLedgerIssueDTO(ticker=i.ticker, on=i.on, message=i.message) for i in year.issues
        ],
    )
