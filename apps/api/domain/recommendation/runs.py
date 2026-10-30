"""Worker side of the lenses and gates (Phases 45.1 and 45.2): the universe of each class, its
lenses and its gates, stored.

The universe (design N2) is every active ARCA asset registered (PORTFOLIO when there is a
position, WATCHLIST otherwise) plus the Garimpo's liquid stocks not registered (CATALOG). All
three compete (decision 10.4). The panel signals of a company are measured on one share class,
the most traded; a registered class of the same company reads them from it, and the other class
does not enter again as a catalog asset. Caixa stays out: fixed income and cash are chosen by
rate and term, not by these lenses.

Everything is read from the database (the screens never compute, Phase 39).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from domain.assets.services.cerrado import CerradoEvaluation
from domain.assets.services.scores import accounting_scores
from domain.disclosures.events import RESTRUCTURING
from domain.disclosures.services.sync import base_ticker
from domain.mining.universe import MIN_DAILY_VOLUME, mining_universe
from domain.policy.services.lifecycle import has_position
from domain.policy.services.policy import current_policy
from domain.portfolio.services.positions import InsufficientQuantityError, build_position
from domain.recommendation.gates import RESTRUCTURING_LOOKBACK_DAYS, AssetGates, asset_gates
from domain.recommendation.lenses import CATALOG, PORTFOLIO, WATCHLIST, asset_lenses
from domain.shared.entities import AssetEntity
from domain.shared.enums import ArcaClass, AssetPurpose, ChecklistProfile, default_arca_class
from domain.shared.unit_of_work import AbstractUnitOfWork
from domain.simulation.data import px_symbol, tr_symbol

Evaluate = Callable[[AbstractUnitOfWork, AssetEntity], CerradoEvaluation]

# Liquidity floor per class (R$ a day); international assets have none here.
REAL_ESTATE_MIN_DAILY_VOLUME = 250_000.0
_FINANCIAL_SECTOR_WORDS = ("financ", "banc", "segur")


def _arca_class(asset: AssetEntity) -> str | None:
    if asset.arca_class is not None:
        return asset.arca_class.value
    try:
        return default_arca_class(asset.asset_type).value
    except (KeyError, TypeError):
        return None


def _ledger_valid(asset: AssetEntity) -> bool:
    if asset.fixed_income_term is not None:
        return True
    try:
        build_position(asset.transactions, events=asset.corporate_events)
    except InsufficientQuantityError:
        return False
    return True


@dataclass(frozen=True)
class _Member:
    ticker: str
    source: str
    arca_class: str | None
    sector: str
    cnpj: str | None
    signal_ticker: str | None
    asset: AssetEntity | None  # None for a catalog asset


def _universe(uow: AbstractUnitOfWork, min_daily_volume: float, panel: set[str]) -> list[_Member]:
    sectors = {i.ticker.upper(): (i.sector or "") for i in uow.catalog.list_all()}
    members = mining_universe(uow, min_daily_volume)
    member_by_cnpj = {m.cnpj: m.ticker for m in members}
    # Caixa (fixed income and cash) is chosen by rate and term, not by these lenses.
    registered = [
        a
        for a in uow.assets.list_all(active_only=True)
        if a.purpose == AssetPurpose.ARCA and _arca_class(a) not in (None, ArcaClass.CAIXA.value)
    ]
    cnpjs = uow.cvm_issuers.cnpjs_for(sorted({base_ticker(a.ticker) for a in registered}))
    out: list[_Member] = []
    seen: set[str] = set()
    for asset in registered:
        ticker = asset.ticker.upper()
        cnpj = cnpjs.get(base_ticker(ticker))
        signal_ticker = member_by_cnpj.get(cnpj) if cnpj else None
        if signal_ticker is None and ticker in panel:
            signal_ticker = ticker
        seen.update({ticker, member_by_cnpj.get(cnpj, ticker) if cnpj else ticker})
        holds = has_position(
            asset.transactions,
            fixed_income=asset.fixed_income_term is not None,
            events=asset.corporate_events,
        )
        out.append(
            _Member(
                ticker,
                PORTFOLIO if holds else WATCHLIST,
                _arca_class(asset),
                sectors.get(ticker, ""),
                cnpj,
                signal_ticker,
                asset,
            )
        )
    for m in members:
        if m.ticker not in seen:
            out.append(
                _Member(m.ticker, CATALOG, ArcaClass.ACOES.value, m.sector, m.cnpj, m.ticker, None)
            )
    return out


def _gates(
    uow: AbstractUnitOfWork, universe: list[_Member], min_daily_volume: float, as_of: date
) -> list[AssetGates]:
    tickers = [m.ticker for m in universe]
    stored = uow.market_data.get_many(tickers)
    catalog_volume = {i.ticker.upper(): i.volume_brl for i in uow.catalog.list_all()}
    statements = uow.fundamentals.list_for_many(tickers)
    since = as_of - timedelta(days=RESTRUCTURING_LOOKBACK_DAYS)
    cnpjs = sorted({m.cnpj for m in universe if m.cnpj})
    restructuring: dict[str, list[date]] = {}
    for doc in uow.cvm_documents.events(cnpjs, since=since) if cnpjs else []:
        if doc.event_class == RESTRUCTURING:
            restructuring.setdefault(doc.cnpj, []).append(doc.delivery_date)
    floors = {
        ArcaClass.ACOES.value: min_daily_volume,
        ArcaClass.REAL_ESTATE.value: REAL_ESTATE_MIN_DAILY_VOLUME,
    }
    out = []
    for m in universe:
        data = stored.get(m.ticker)
        fund = data.fundamentals if data else None
        volume = (fund.avg_daily_volume if fund else None) or catalog_volume.get(m.ticker)
        span = uow.market_series.date_range(px_symbol(m.ticker)) or uow.market_series.date_range(
            tr_symbol(m.ticker)
        )
        if m.asset is not None:
            applies_altman = m.asset.profile == ChecklistProfile.STOCK
        else:
            applies_altman = not any(w in m.sector.lower() for w in _FINANCIAL_SECTOR_WORDS)
        out.append(
            asset_gates(
                ticker=m.ticker,
                as_of=as_of,
                ledger_valid=_ledger_valid(m.asset) if m.asset is not None else None,
                volume=volume,
                liquidity_floor=floors.get(m.arca_class or ""),
                first_price=span[0] if span else None,
                altman=accounting_scores(statements.get(m.ticker, [])).z_score,
                applies_altman=applies_altman,
                restructuring=restructuring.get(m.cnpj or "", []),
                suspicious=dict(fund.suspicious) if fund is not None else None,
            )
        )
    return out


def refresh_lenses(
    uow: AbstractUnitOfWork,
    evaluate: Evaluate,
    *,
    min_daily_volume: float = MIN_DAILY_VOLUME,
    today: date | None = None,
) -> dict[str, Any]:
    """Compute and store the lenses and the gates of every asset of the universe."""
    as_of = today or date.today()
    validity = current_policy(uow.policies).eligibility.answer_validity_months
    month = uow.mining.latest_signal_month()
    panel: dict[str, dict[str, float]] = {}
    for s in uow.mining.signals_of_month(month) if month else []:
        panel.setdefault(s.ticker, {})[s.signal] = s.z
    universe = _universe(uow, min_daily_volume, set(panel))
    items = []
    for m in universe:
        stored = uow.forecasts.latest(m.ticker) if m.asset is not None else None
        items.append(
            asset_lenses(
                ticker=m.ticker,
                as_of=as_of,
                source=m.source,
                arca_class=m.arca_class,
                sector=m.sector,
                evaluation=evaluate(uow, m.asset) if m.asset is not None else None,
                validity_months=validity,
                signals=panel.get(m.signal_ticker, {}) if m.signal_ticker else {},
                signal_month=month,
                forecast={**stored.payload, "as_of": stored.as_of.isoformat()} if stored else None,
                signal_ticker=m.signal_ticker,
            )
        )
    gates = _gates(uow, universe, min_daily_volume, as_of)
    stored_count = uow.recommendation.replace_lenses(as_of, items)
    uow.recommendation.replace_gates(as_of, gates)
    registered = sum(1 for m in universe if m.asset is not None)
    return {
        "assets": stored_count,
        "registered": registered,
        "catalog": stored_count - registered,
        "eligible": sum(1 for g in gates if g.eligible),
        "signal_month": month.isoformat() if month else None,
    }
