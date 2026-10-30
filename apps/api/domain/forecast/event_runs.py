"""Worker side of the event study (Phase 42.4): measure every event and store the study, with
the out-of-sample gate of each class that decides what enters the forecast (Phase 42.5).

The companies are those of the mining universe (liquid stocks with a CNPJ) plus the registered
Brazilian stocks; each company is measured on one ticker, the mining one when it has it. The
prices are the daily total returns stored by the long-history loads, the market the Ibovespa.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from domain.disclosures.services.sync import base_ticker
from domain.forecast.events import align, gate, group_events, measure, study
from domain.mining.universe import MIN_DAILY_VOLUME, mining_universe
from domain.shared.enums import AssetType
from domain.shared.unit_of_work import AbstractUnitOfWork
from domain.simulation.data import SIMULATION_HISTORY_START, index_symbol, tr_symbol

EVENTS = "EVENTS"


def _series(uow: AbstractUnitOfWork, symbol: str, end: date) -> list[tuple[date, float]]:
    return [
        (p.reference_date, p.value)
        for p in uow.market_series.list_series(
            symbol, date_from=SIMULATION_HISTORY_START, date_to=end
        )
    ]


def company_tickers(uow: AbstractUnitOfWork, min_daily_volume: float) -> dict[str, str]:
    """CNPJ -> the ticker its events are measured on."""
    out = {m.cnpj: m.ticker for m in mining_universe(uow, min_daily_volume)}
    stocks = [
        a for a in uow.assets.list_all(active_only=True) if a.asset_type == AssetType.STOCK_BR
    ]
    mapped = uow.cvm_issuers.cnpjs_for([base_ticker(a.ticker) for a in stocks])
    for asset in stocks:
        cnpj = mapped.get(base_ticker(asset.ticker))
        if cnpj and cnpj not in out:
            out[cnpj] = asset.ticker.upper()
    return out


def run_event_study(
    uow: AbstractUnitOfWork,
    *,
    min_daily_volume: float = MIN_DAILY_VOLUME,
    today: date | None = None,
) -> dict[str, Any] | None:
    """Measure the events of the companies with prices and store the effects and the study."""
    as_of = today or date.today()
    tickers = company_tickers(uow, min_daily_volume)
    market = _series(uow, index_symbol("IBOV"), as_of)
    if not tickers or len(market) < 2:
        return None
    documents = uow.cvm_documents.events(sorted(tickers))
    rows = [
        (d.id, tickers[d.cnpj], d.delivery_date, d.event_class or "")
        for d in documents
        if d.id is not None and d.cnpj in tickers
    ]
    effects = []
    by_ticker: dict[str, list] = {}
    for event in group_events(rows):
        by_ticker.setdefault(event.ticker, []).append(event)
    cnpj_of = {t: c for c, t in tickers.items()}
    for ticker, events in by_ticker.items():
        returns = align(_series(uow, tr_symbol(ticker), as_of), market)
        if not returns.dates:
            continue
        results = [d.delivered_on for d in uow.cvm_statements.docs_for(cnpj_of[ticker])]
        for event in events:
            effects.extend(measure(event, returns, results))
    uow.cvm_documents.replace_effects(effects)
    found = gate(effects, study(effects, as_of=as_of))
    payload = found.to_dict()
    uow.forecasts.save_model(EVENTS, as_of, payload)
    return payload
