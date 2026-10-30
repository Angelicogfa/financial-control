"""Read the statements delivered to the CVM by an asset's company (Phase 42.2).

The screen reads only the stored statements (`cvm_statements`) and the stored quote: one row per
delivery, with what was known right after it (12-month flows and the last balance), and the
indicators of the last delivery at today's price.
"""

from __future__ import annotations

from controllers.disclosures.responses import (
    AssetStatementsDTO,
    StatementDeliveryDTO,
    StatementValuationDTO,
)
from controllers.shared.dependencies import UoWFactory
from core.errors import NotFoundError
from domain.disclosures.services.sync import base_ticker, company_assets
from domain.disclosures.statements import (
    DIVIDENDS_PAID,
    EBIT,
    FINANCIAL,
    NET_INCOME,
    REVENUE,
    SHARES,
    TOTAL_ASSETS,
    PitFundamentals,
    delivery_history,
)
from domain.forecast.valuation_pit import valuation

MAX_DELIVERIES = 40  # ten years of quarters


def _delivery(pit: PitFundamentals) -> StatementDeliveryDTO:
    return StatementDeliveryDTO(
        reference_date=pit.reference_date,
        delivered_on=pit.delivered_on,
        doc_type=pit.doc_type,  # type: ignore[arg-type]
        version=pit.version,
        revenue=pit.get(REVENUE),
        ebit=pit.get(EBIT),
        ebitda=pit.ebitda,
        net_income=pit.get(NET_INCOME),
        dividends_paid=pit.get(DIVIDENDS_PAID),
        equity=pit.controlling_equity,
        net_debt=pit.net_debt,
        total_assets=pit.get(TOTAL_ASSETS),
        shares_outstanding=pit.get(SHARES),
    )


class StatementsHandler:
    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def get(self, asset_id: int) -> AssetStatementsDTO:
        with self.uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if asset is None:
                raise NotFoundError(f"Asset id={asset_id} not found")
            base = {"asset_id": asset_id, "ticker": asset.ticker}
            if not company_assets([asset]):
                return AssetStatementsDTO(
                    **base,
                    status="NOT_A_COMPANY",
                    notes=["Só ações de empresas brasileiras entregam balanços à CVM."],
                )
            ticker = base_ticker(asset.ticker)
            cnpj = uow.cvm_issuers.cnpjs_for([ticker]).get(ticker)
            if cnpj is None:
                return AssetStatementsDTO(
                    **base,
                    status="NOT_MAPPED",
                    notes=[
                        f"{ticker} ainda não está no cadastro de códigos da CVM; a carga dos "
                        "comunicados da CVM atualiza esse cadastro."
                    ],
                )
            facts = uow.cvm_statements.facts_for(cnpj)
            years = sorted({load.year for load in uow.cvm_statements.loads()})
            quote_data = uow.market_data.get_many([asset.ticker]).get(asset.ticker.upper())
        if not facts:
            return AssetStatementsDTO(
                **base,
                status="NOT_LOADED",
                cnpj=cnpj,
                years_loaded=years,
                notes=[
                    "Os balanços desta empresa ainda não foram carregados; a carga diária traz "
                    "os dois últimos anos e o histórico desde 2010 aos poucos."
                ],
            )
        history = delivery_history(facts)
        latest = history[0]
        quote = quote_data.quote if quote_data else None
        priced = None
        if quote is not None and quote.price > 0:
            found = valuation(latest, quote.price)
            if found is not None:
                priced = StatementValuationDTO(
                    price=quote.price,
                    price_date=(
                        quote.market_time.date()
                        if quote.market_time
                        else quote_data.quote_fetched_at.date()
                        if quote_data and quote_data.quote_fetched_at
                        else None
                    ),
                    market_cap=found.market_cap,
                    earnings_yield=found.earnings_yield,
                    dividend_yield=found.dividend_yield,
                    price_to_book=found.price_to_book,
                    ev_to_ebitda=found.ev_to_ebitda,
                )
        notes = [
            "Cada linha mostra o que se sabia logo depois da entrega: resultados dos últimos 12 "
            "meses e o balanço da data de referência.",
            "Valores consolidados quando a empresa os publica; da controladora, quando não.",
        ]
        if latest.template == FINANCIAL:
            notes.append(
                "Banco ou seguradora: receita, EBIT, EBITDA e dívida líquida não se aplicam."
            )
        return AssetStatementsDTO(
            **base,
            status="OK",
            cnpj=cnpj,
            template=latest.template,  # type: ignore[arg-type]
            deliveries=[_delivery(p) for p in history[:MAX_DELIVERIES]],
            valuation=priced,
            years_loaded=years,
            notes=notes,
        )
