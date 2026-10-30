"""Use cases of the recommendation (Phase 45): read what the worker stored."""

from __future__ import annotations

from collections import Counter

from controllers.recommendation.responses import AssetLensesDTO, GateDTO, LensBoardDTO, LensDTO
from controllers.shared.dependencies import UoWFactory
from domain.recommendation.gates import GATE_LABELS, AssetGates
from domain.recommendation.lenses import LENS_LABELS, AssetLenses


def _asset_dto(item: AssetLenses, gates: AssetGates | None) -> AssetLensesDTO:
    return AssetLensesDTO(
        ticker=item.ticker,
        source=item.source,  # type: ignore[arg-type]
        arca_class=item.arca_class,
        sector=item.sector,
        signal_ticker=item.signal_ticker,
        lenses=[
            LensDTO(
                lens=s.lens,  # type: ignore[arg-type]
                label=LENS_LABELS.get(s.lens, s.lens),
                value=s.value,
                normalized=s.normalized,
                confidence=s.confidence,
                note=s.note,
                flags=s.flags,
            )
            for s in item.lenses
        ],
        eligible=gates.eligible if gates is not None else None,
        gates=[
            GateDTO(
                gate=r.gate,  # type: ignore[arg-type]
                label=GATE_LABELS.get(r.gate, r.gate),
                status=r.status,  # type: ignore[arg-type]
                reason=r.reason,
            )
            for r in (gates.results if gates is not None else [])
        ],
    )


class RecommendationHandler:
    def __init__(self, uow_factory: UoWFactory) -> None:
        self.uow_factory = uow_factory

    def lenses(
        self,
        *,
        arca_class: str | None = None,
        source: str | None = None,
        ticker: str | None = None,
        eligible: bool | None = None,
    ) -> LensBoardDTO:
        """The latest lenses and gates, optionally of one class, source, ticker or eligibility."""
        tickers = [ticker] if ticker else None
        with self.uow_factory() as uow:
            items = uow.recommendation.lenses(tickers=tickers)
            gates = {g.ticker: g for g in uow.recommendation.gates(tickers=tickers)}
        if not items:
            return LensBoardDTO(status="NOT_COMPUTED")
        chosen = [
            i
            for i in items
            if (arca_class is None or i.arca_class == arca_class)
            and (source is None or i.source == source)
            and (eligible is None or (i.ticker in gates and gates[i.ticker].eligible == eligible))
        ]
        return LensBoardDTO(
            status="OK",
            as_of=items[0].as_of,
            assets=[_asset_dto(i, gates.get(i.ticker)) for i in chosen],
            counts=dict(Counter(i.source for i in chosen)),
            eligible=sum(1 for i in chosen if i.ticker in gates and gates[i.ticker].eligible),
        )
