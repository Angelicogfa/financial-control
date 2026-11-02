"""Instrument page and global search (Phase 48.R2): any ticker, registered or not.

Both handlers only read the database. A ticker the worker never fetched still opens with
what the B3 catalog has (name, sector, close of the last session); no provider is called
during the request (rule of Phase 39).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable

from core.errors import NotFoundError, ValidationError
from domain.forecast.model import PriceForecast
from domain.forecast.services import MIN_SEAL_LEVEL, forecast_seal
from domain.instruments.read_models import (
    ForecastBand,
    InstrumentForecast,
    InstrumentIndicators,
    InstrumentKey,
    InstrumentKind,
    InstrumentLens,
    InstrumentLenses,
    InstrumentQuote,
    InstrumentTracking,
    InstrumentView,
    MatchKind,
    QuoteSource,
    SearchHit,
    SearchResult,
    TreasuryTerms,
    instrument_key,
)
from domain.market.entities import StoredMarketData, TreasuryBond
from domain.market.services.price_chart import PRICE_RANGES, PriceChart, price_chart
from domain.market.services.stored import range_start
from domain.policy.services.lifecycle import has_position
from domain.shared.entities import AssetEntity, CatalogInstrument
from domain.shared.unit_of_work import AbstractUnitOfWork, UoWFactory

FORECAST_BAND_MONTHS = (3, 6, 12, 24)
MAX_SEARCH_LIMIT = 50
MAX_QUERY_LENGTH = 64
_MATCH_RANK = {kind: i for i, kind in enumerate(MatchKind)}


def _holds(asset: AssetEntity) -> bool:
    return has_position(
        asset.transactions,
        fixed_income=asset.fixed_income_term is not None,
        events=asset.corporate_events,
    )


def _tracking(asset: AssetEntity | None) -> InstrumentTracking | None:
    if asset is None or asset.id is None:
        return None
    return InstrumentTracking(
        asset_id=asset.id,
        is_active=asset.is_active,
        holds_position=_holds(asset),
        arca_class=asset.arca_class.value if asset.arca_class else None,
        purpose=asset.purpose.value,
    )


def _quote(
    stored: StoredMarketData | None,
    catalog: CatalogInstrument | None,
    asset: AssetEntity | None,
) -> InstrumentQuote | None:
    if stored is not None and stored.quote is not None and stored.quote.price > 0:
        q = stored.quote
        return InstrumentQuote(
            price=q.price,
            currency=q.currency,
            source=QuoteSource.STORED_QUOTE,
            change_pct=q.change_pct,
            as_of=q.market_time or stored.quote_fetched_at,
            freshness=q.freshness.value,
        )
    if catalog is not None and catalog.close:
        return InstrumentQuote(
            price=catalog.close,
            currency="BRL",
            source=QuoteSource.CATALOG_CLOSE,
            change_pct=catalog.change_pct,
            as_of=catalog.updated_at,
        )
    if asset is not None and asset.manual_price:
        return InstrumentQuote(
            price=float(asset.manual_price),
            currency=asset.currency or "BRL",
            source=QuoteSource.MANUAL,
        )
    return None


def _indicators(stored: StoredMarketData | None) -> InstrumentIndicators | None:
    if stored is None or stored.fundamentals is None:
        return None
    f = stored.fundamentals
    return InstrumentIndicators(
        fetched_at=stored.fundamentals_fetched_at,
        price_to_earnings=f.price_to_earnings,
        price_to_book=f.price_to_book,
        dividend_yield=f.dividend_yield,
        return_on_equity=f.return_on_equity,
        profit_margin=f.profit_margin,
        net_debt_to_ebitda=f.net_debt_to_ebitda,
        market_cap=f.market_cap,
        avg_daily_volume=f.avg_daily_volume,
        suspicious=bool(f.suspicious),
    )


def _lenses(uow: AbstractUnitOfWork, ticker: str) -> InstrumentLenses | None:
    found = uow.recommendation.lenses(tickers=[ticker])
    if not found:
        return None
    item = found[0]
    gates = {g.ticker: g for g in uow.recommendation.gates(as_of=item.as_of, tickers=[ticker])}
    gate = gates.get(ticker)
    return InstrumentLenses(
        as_of=item.as_of,
        source=item.source,
        arca_class=item.arca_class,
        sector=item.sector,
        eligible=gate.eligible if gate is not None else None,
        items=[
            InstrumentLens(
                lens=s.lens, normalized=s.normalized, confidence=s.confidence, note=s.note
            )
            for s in item.lenses
        ],
    )


def _forecast(uow: AbstractUnitOfWork, ticker: str) -> InstrumentForecast:
    """The stored forecast, shown only from the "Use com cautela" seal (decision 42.0-5)."""
    seal = forecast_seal(uow.forecasts.latest_calibration())
    stored = uow.forecasts.latest(ticker)
    base = {"seal_level": seal.level, "seal_label": seal.label}
    if stored is None:
        return InstrumentForecast(status="NOT_COMPUTED", **base)
    if stored.payload.get("status") != "OK":
        return InstrumentForecast(status="INSUFFICIENT_HISTORY", as_of=stored.as_of, **base)
    requested = bool(stored.payload.get("on_demand"))
    if seal.level < MIN_SEAL_LEVEL and not requested:
        return InstrumentForecast(status="LOW_CONFIDENCE", as_of=stored.as_of, **base)
    forecast = PriceForecast.from_dict(stored.payload)
    return InstrumentForecast(
        status="OK",
        as_of=forecast.as_of,
        price_now=forecast.price_now,
        bands=[
            ForecastBand(
                months=h.months,
                p5=round(h.price_at(0.05), 2),
                p50=round(h.price_at(0.50), 2),
                p95=round(h.price_at(0.95), 2),
                up_probability=h.up.value,
            )
            for h in forecast.horizons
            if h.months in FORECAST_BAND_MONTHS
        ],
        **base,
    )


def _treasury_view(bond: TreasuryBond, key: InstrumentKey) -> InstrumentView:
    price = bond.buy_price or bond.sell_price or bond.base_price
    return InstrumentView(
        key=key.value,
        kind=InstrumentKind.TREASURY,
        ticker=bond.symbol,
        name=bond.name,
        asset_type="TREASURY",
        sector=None,
        logo_url=None,
        in_catalog=True,
        quote=(
            InstrumentQuote(
                price=price,
                currency="BRL",
                source=QuoteSource.TREASURY_PRICE,
                as_of=bond.updated_at,
            )
            if price
            else None
        ),
        indicators=None,
        lenses=None,
        forecast=None,
        tracking=None,
        treasury=TreasuryTerms(
            bond_type=bond.bond_type,
            maturity_date=bond.maturity_date,
            indexer=bond.indexer.value,
            liquidity=bond.liquidity.value,
            buy_rate=bond.buy_rate,
            sell_rate=bond.sell_rate,
            buy_price=bond.buy_price,
            sell_price=bond.sell_price,
            base_date=bond.base_date,
        ),
        data_gaps=[] if price else ["O Tesouro não publicou preço deste título hoje."],
    )


def _gaps(view_quote: InstrumentQuote | None, stored: StoredMarketData | None) -> list[str]:
    gaps: list[str] = []
    if view_quote is None:
        gaps.append("Ainda não há cotação guardada deste ativo.")
    elif view_quote.source == QuoteSource.CATALOG_CLOSE:
        gaps.append(
            "Preço do fechamento do catálogo da B3; a cotação do dia ainda não foi buscada."
        )
    if stored is None or stored.fundamentals is None:
        gaps.append("Os indicadores deste ativo ainda não foram buscados.")
    if stored is None or stored.history_loaded_at is None:
        gaps.append("O histórico de preço ainda não foi carregado.")
    return gaps


class InstrumentHandler:
    """`GET /instruments/{key}`: the instrument page for a ticker or a Tesouro symbol."""

    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def view(self, raw_key: str) -> InstrumentView:
        key = instrument_key(raw_key)
        with self.uow_factory() as uow:
            if key.kind == InstrumentKind.TREASURY:
                bond = uow.treasury_catalog.get(key.value)
                if bond is None:
                    raise NotFoundError(
                        f"Tesouro bond {key.value} not found", code="INSTRUMENT_NOT_FOUND"
                    )
                return _treasury_view(bond, key)
            ticker = key.value
            catalog = uow.catalog.get(ticker)
            asset = uow.assets.get_by_ticker(ticker)
            stored = uow.market_data.get_many([ticker]).get(ticker)
            known = stored is not None and (
                stored.quote is not None or stored.fundamentals is not None
            )
            if catalog is None and asset is None and not known:
                raise NotFoundError(f"Instrument {ticker} not found", code="INSTRUMENT_NOT_FOUND")
            quote = _quote(stored, catalog, asset)
            fundamentals = stored.fundamentals if stored is not None else None
            stored_name = stored.quote.name if stored is not None and stored.quote else None
            return InstrumentView(
                key=ticker,
                kind=InstrumentKind.LISTED,
                ticker=ticker,
                name=(asset.name if asset else None)
                or (catalog.name if catalog else None)
                or stored_name
                or ticker,
                asset_type=(
                    asset.asset_type.value
                    if asset
                    else catalog.asset_type.value
                    if catalog and catalog.asset_type
                    else None
                ),
                sector=(catalog.sector if catalog else None)
                or (fundamentals.sector if fundamentals else None),
                logo_url=(catalog.logo_url if catalog else None)
                or (stored.quote.logo_url if stored is not None and stored.quote else None),
                in_catalog=catalog is not None,
                quote=quote,
                indicators=_indicators(stored),
                lenses=_lenses(uow, ticker),
                forecast=_forecast(uow, ticker),
                tracking=_tracking(asset),
                treasury=None,
                data_gaps=_gaps(quote, stored),
            )

    def prices(self, raw_key: str, range_period: str) -> PriceChart:
        """Stored daily closes of one period, cleaned like the asset chart."""
        if range_period not in PRICE_RANGES:
            raise ValidationError(f"range must be one of {', '.join(PRICE_RANGES)}")
        key = instrument_key(raw_key)
        if key.kind == InstrumentKind.TREASURY:
            return price_chart(range_period, [])
        with self.uow_factory() as uow:
            found = uow.price_history.list_for_many(
                [key.value], date_from=range_start(range_period)
            )
        return price_chart(range_period, found.get(key.value, []))


def fold(text: str) -> str:
    """Case- and accent-insensitive form used to match the query."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold().strip()


def match_kind(query: str, ticker: str, name: str) -> MatchKind | None:
    """How a folded query matches a candidate, best first; None when it does not."""
    t, n = fold(ticker), fold(name)
    if t == query:
        return MatchKind.TICKER_EXACT
    if t.startswith(query):
        return MatchKind.TICKER_PREFIX
    words = n.replace("-", " ").split()
    if n.startswith(query) or any(w.startswith(query) for w in words):
        return MatchKind.NAME_PREFIX
    if query in n:
        return MatchKind.NAME_CONTAINS
    return None


class SearchHandler:
    """`GET /search`: registered assets, the B3 catalog and the Tesouro catalog at once."""

    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def search(self, query: str, *, limit: int = 10) -> SearchResult:
        q = fold(query)
        if not q:
            raise ValidationError("query must not be empty", code="EMPTY_QUERY")
        if len(q) > MAX_QUERY_LENGTH:
            raise ValidationError(f"query longer than {MAX_QUERY_LENGTH} characters")
        limit = max(1, min(limit, MAX_SEARCH_LIMIT))
        with self.uow_factory() as uow:
            assets = {a.ticker: a for a in uow.assets.list_all(active_only=False)}
            catalog = uow.catalog.list_all()
            bonds = uow.treasury_catalog.list_all()
        hits = list(_candidates(q, assets, catalog, bonds))
        volume = {c.ticker: c.volume_brl or 0.0 for c in catalog}
        hits.sort(
            key=lambda h: (
                _MATCH_RANK[h.match],
                not h.holds_position,
                h.tracked_asset_id is None,
                -volume.get(h.ticker, 0.0),
                h.ticker,
            )
        )
        return SearchResult(query=query.strip(), hits=hits[:limit], total=len(hits))


def _candidates(
    q: str,
    assets: dict[str, AssetEntity],
    catalog: Iterable[CatalogInstrument],
    bonds: Iterable[TreasuryBond],
) -> Iterable[SearchHit]:
    seen: set[str] = set()
    for item in catalog:
        asset = assets.get(item.ticker)
        name = asset.name if asset else item.name
        kind = match_kind(q, item.ticker, name) or match_kind(q, item.ticker, item.name)
        if kind is None:
            continue
        seen.add(item.ticker)
        yield SearchHit(
            key=item.ticker,
            kind=InstrumentKind.LISTED,
            ticker=item.ticker,
            name=name,
            asset_type=(
                asset.asset_type.value
                if asset
                else item.asset_type.value
                if item.asset_type
                else None
            ),
            sector=item.sector,
            close=item.close,
            match=kind,
            tracked_asset_id=asset.id if asset else None,
            holds_position=_holds(asset) if asset else False,
        )
    for ticker, asset in assets.items():
        if ticker in seen:
            continue
        kind = match_kind(q, ticker, asset.name)
        if kind is None:
            continue
        yield SearchHit(
            key=ticker,
            kind=InstrumentKind.LISTED,
            ticker=ticker,
            name=asset.name,
            asset_type=asset.asset_type.value,
            sector=None,
            close=float(asset.manual_price) if asset.manual_price else None,
            match=kind,
            tracked_asset_id=asset.id,
            holds_position=_holds(asset),
        )
    for bond in bonds:
        kind = match_kind(q, bond.symbol, bond.name)
        if kind is None:
            continue
        yield SearchHit(
            key=bond.symbol,
            kind=InstrumentKind.TREASURY,
            ticker=bond.symbol,
            name=bond.name,
            asset_type="TREASURY",
            sector=None,
            close=bond.buy_price or bond.sell_price,
            match=kind,
        )
