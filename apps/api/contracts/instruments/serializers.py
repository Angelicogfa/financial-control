"""Read model -> response schema of the instrument page and of the search (Phase 48.R2)."""

from __future__ import annotations

from dataclasses import asdict

from contracts.assets.responses import AssetPriceHistoryDTO, DatedPriceDTO, PricePointDTO
from contracts.instruments.responses import InstrumentViewDTO, SearchResultDTO
from domain.instruments.read_models import InstrumentView, SearchResult
from domain.market.services.price_chart import PriceChart


def to_instrument_view_dto(view: InstrumentView) -> InstrumentViewDTO:
    return InstrumentViewDTO.model_validate(asdict(view))


def to_search_result_dto(result: SearchResult) -> SearchResultDTO:
    return SearchResultDTO.model_validate(asdict(result))


def to_price_history_dto(chart: PriceChart) -> AssetPriceHistoryDTO:
    return AssetPriceHistoryDTO(
        range=chart.range_period,
        points=[PricePointDTO(date=d, close=c) for d, c in chart.points],
        change=chart.change,
        high=DatedPriceDTO(date=chart.high[0], price=chart.high[1]) if chart.high else None,
        low=DatedPriceDTO(date=chart.low[0], price=chart.low[1]) if chart.low else None,
        dropped_spikes=chart.dropped_spikes,
    )
