"""Use cases (query handlers) for the tax module.

Scope: tax rule registry, per-asset tax status (item 24.2) and the taxed vs. exempt fixed
income comparator (item 24.3).
"""

from __future__ import annotations

from datetime import date

from controllers.shared.dependencies import UoWFactory
from controllers.tax.requests import FixedIncomeCompareRequest, FixedIncomeOfferRequest
from controllers.tax.responses import AssetTaxStatusDTO, FixedIncomeComparisonDTO, TaxRuleDTO
from controllers.tax.serializers import (
    to_asset_tax_status_dto,
    to_comparison_dto,
    to_tax_rule_dto,
)
from core.errors import NotFoundError, ValidationError
from domain.portfolio.services.service import PortfolioApplicationService
from domain.shared.enums import FixedIncomeIndexer, FixedIncomeLiquidity
from domain.shared.unit_of_work import AbstractUnitOfWork
from domain.tax.services.comparator import (
    FixedIncomeOffer,
    OfferIndexer,
    RateScenario,
    compare_offers,
    default_scenarios,
)
from domain.tax.services.status import asset_tax_status

DEFAULT_OPEN_TERM_DAYS = 365

# Tesouro Selic and Selic-indexed bonds are compared as % of CDI (Selic ~ CDI).
OFFER_INDEXER_BY_TERM: dict[FixedIncomeIndexer, OfferIndexer] = {
    FixedIncomeIndexer.CDI: OfferIndexer.CDI_PERCENT,
    FixedIncomeIndexer.SELIC: OfferIndexer.CDI_PERCENT,
    FixedIncomeIndexer.IPCA: OfferIndexer.IPCA_SPREAD,
    FixedIncomeIndexer.PRE: OfferIndexer.PRE,
}


class TaxHandler:
    """Application handler for tax queries (opens UoW boundaries, delegates to pure services)."""

    def __init__(
        self, uow_factory: UoWFactory, portfolio_service: PortfolioApplicationService
    ) -> None:
        self.uow_factory = uow_factory
        self.portfolio_service = portfolio_service

    def list_rules(self) -> list[TaxRuleDTO]:
        with self.uow_factory() as uow:
            book = self.portfolio_service.tax_rules(uow)
        return [to_tax_rule_dto(rule) for rule in book.rules]

    def asset_tax_status(
        self, asset_id: int, *, as_of_date: date | None = None
    ) -> AssetTaxStatusDTO:
        ref_date = as_of_date or date.today()
        with self.uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if asset is None:
                raise NotFoundError(f"Asset id={asset_id} not found")
            curves = self.portfolio_service.ledger_curves(uow, asset, ref_date)
            status = asset_tax_status(
                asset, ref_date, curves=curves, rules=self.portfolio_service.tax_rules(uow)
            )
        return to_asset_tax_status_dto(status)

    def compare_fixed_income(self, req: FixedIncomeCompareRequest) -> FixedIncomeComparisonDTO:
        start = req.start_date or date.today()
        with self.uow_factory() as uow:
            offers = [
                _resolve_offer(uow, item, index, start) for index, item in enumerate(req.offers)
            ]
            rules = self.portfolio_service.tax_rules(uow)
            if req.scenarios:
                scenarios = tuple(
                    RateScenario(s.name, s.annual_cdi_rate, s.annual_ipca_rate)
                    for s in req.scenarios
                )
            else:
                market_cdi, market_ipca = self.portfolio_service.gateway.get_macro_rates()
                premises = self.portfolio_service.load_policy(uow).valuation.projections
                scenarios = default_scenarios(market_cdi, market_ipca, premises)
        comparison = compare_offers(
            offers, scenarios, as_of_date=start, principal=req.principal, rules=rules
        )
        return to_comparison_dto(comparison, offers, [item.asset_id for item in req.offers])


def _resolve_offer(
    uow: AbstractUnitOfWork, item: FixedIncomeOfferRequest, index: int, start: date
) -> FixedIncomeOffer:
    """Offer typed by hand, or completed from a portfolio asset's fixed income terms."""
    label = item.label
    indexer, rate, term_days = item.indexer, item.rate, item.term_days
    tax_exempt, grace_days = item.tax_exempt, item.grace_days
    if item.asset_id is not None:
        asset = uow.assets.get_by_id(item.asset_id)
        if asset is None:
            raise NotFoundError(f"Asset id={item.asset_id} not found")
        term = asset.fixed_income_term
        if term is None:
            raise ValidationError(
                f"Asset {asset.ticker} has no fixed income terms to compare",
                code="ASSET_WITHOUT_FIXED_INCOME_TERM",
            )
        remaining = (
            (term.maturity_date - start).days
            if term.maturity_date is not None
            else DEFAULT_OPEN_TERM_DAYS
        )
        if remaining < 1 and term_days is None:
            raise ValidationError(f"Asset {asset.ticker} has already matured", code="ASSET_MATURED")
        label = label or asset.ticker
        indexer = indexer or OFFER_INDEXER_BY_TERM[term.indexer]
        rate = rate if rate is not None else float(term.contracted_rate)
        term_days = term_days or remaining
        tax_exempt = term.tax_exempt if tax_exempt is None else tax_exempt
        if grace_days is None:
            grace_days = 0 if term.liquidity == FixedIncomeLiquidity.DAILY else term_days
    if indexer is None or rate is None or term_days is None:
        raise ValidationError(
            f"Offer {index + 1} needs indexer, rate and term_days (or an asset_id)",
            code="INCOMPLETE_OFFER",
        )
    return FixedIncomeOffer(
        label=label or f"Título {index + 1}",
        indexer=indexer,
        rate=rate,
        term_days=term_days,
        tax_exempt=bool(tax_exempt),
        grace_days=min(grace_days or 0, term_days),
    )
